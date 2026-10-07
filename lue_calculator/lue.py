# -*- coding: utf-8 -*-
"""
LUE 测量引擎（光利用效率）

提供两种 LUE 计算模式：
1. 传统 LUE (LUE_Traditional)：AVT_Human × PCE
2. 植物 LUE (LUE_Plant)：AVT_Plant × PCE

核心公式：
    LUE = AVT × PCE
    
其中：
    - AVT：平均可见光透过率（百分比）
    - PCE：光电转换效率（百分比）
    
LUE 表示半透明光伏器件在满足透光需求的同时发电的综合效率指标。
"""

import numpy as np
from datetime import datetime
from typing import Dict, List, Optional, Union, Tuple
from pathlib import Path
from dataclasses import dataclass
from enum import Enum

from .data_parser import (
    parse_spectrum_file,
    parse_performance_file,
    absorbance_to_transmittance,
    match_sample_files,
    match_abs_t_pairs
)
from .avt import AVTEngine, AVTResult


class LUEMode(Enum):
    """LUE 计算模式"""
    TRADITIONAL = "traditional"  # 传统模式（人眼响应）
    PLANT = "plant"              # 植物模式
    BOTH = "both"                # 同时计算两种


@dataclass
class LUEResult:
    """LUE 计算结果"""
    mode: str                    # 计算模式
    lue: float                   # LUE 值（百分比）
    avt: float                   # AVT 值（百分比）
    pce: float                   # PCE 值（百分比）
    sample_name: str = None      # 样品名称
    avt_details: AVTResult = None  # AVT 计算详情
    
    def __str__(self) -> str:
        return f"LUE ({self.mode}): {self.lue:.2f}% = AVT({self.avt:.2f}%) × PCE({self.pce:.2f}%)"


@dataclass
class FullAnalysisResult:
    """完整分析结果"""
    sample_name: str
    lue_traditional: LUEResult
    lue_plant: LUEResult
    performance: Dict[str, float]
    wavelengths: np.ndarray = None
    transmittance: np.ndarray = None


class LUEEngine:
    """
    LUE 测量引擎
    
    用法示例：
        # 方式1：直接从 AVT 和 PCE 计算
        engine = LUEEngine()
        lue = engine.calculate(avt=45.0, pce=12.5)
        
        # 方式2：从透过率和 PCE 计算
        lue = engine.calculate_from_spectrum(wavelengths, transmittance, pce=12.5)
        
        # 方式3：从文件计算完整分析
        result = engine.analyze_sample(spectrum_file, performance_file)
        
        # 方式4：批量处理
        results = engine.batch_analyze(spectrum_dir, performance_dir)
    """
    
    def __init__(self):
        """初始化 LUE 引擎"""
        self.avt_engine = AVTEngine()
    
    def calculate(
        self, 
        avt: float, 
        pce: float,
        mode: Union[str, LUEMode] = 'traditional'
    ) -> float:
        """
        计算 LUE 值
        
        参数：
            avt: 平均可见光透过率（百分比）
            pce: 光电转换效率（百分比）
            mode: 计算模式（仅用于标记，实际计算相同）
            
        返回：
            LUE 值（百分比）
        """
        # LUE = AVT × PCE / 100（因为两者都是百分比）
        return avt * pce / 100.0
    
    def calculate_from_spectrum(
        self, 
        wavelengths: np.ndarray, 
        transmittance: np.ndarray,
        pce: float,
        mode: Union[str, LUEMode] = 'both',
        return_details: bool = False
    ) -> Union[float, Dict[str, LUEResult]]:
        """
        从透过率光谱和 PCE 计算 LUE
        
        参数：
            wavelengths: 波长数组 (nm)
            transmittance: 透过率数组 (0-1 范围)
            pce: 光电转换效率（百分比）
            mode: 计算模式 ('traditional', 'plant', 或 'both')
            return_details: 是否返回详细结果
            
        返回：
            LUE 值或包含详细结果的字典
        """
        if isinstance(mode, LUEMode):
            mode = mode.value
        
        if mode == 'both':
            avt_results = self.avt_engine.calculate_both(
                wavelengths, transmittance, return_details=True
            )
            
            lue_trad = self.calculate(avt_results['human'].avt, pce)
            lue_plant = self.calculate(avt_results['plant'].avt, pce)
            
            if return_details:
                return {
                    'traditional': LUEResult(
                        mode='traditional',
                        lue=lue_trad,
                        avt=avt_results['human'].avt,
                        pce=pce,
                        avt_details=avt_results['human']
                    ),
                    'plant': LUEResult(
                        mode='plant',
                        lue=lue_plant,
                        avt=avt_results['plant'].avt,
                        pce=pce,
                        avt_details=avt_results['plant']
                    )
                }
            else:
                return {'traditional': lue_trad, 'plant': lue_plant}
        
        else:
            # 单模式计算
            avt_mode = 'human' if mode == 'traditional' else 'plant'
            avt_result = self.avt_engine.calculate(
                wavelengths, transmittance, avt_mode, return_details=True
            )
            
            avt_val = avt_result.avt if isinstance(avt_result, AVTResult) else avt_result
            lue = self.calculate(avt_val, pce)
            
            if return_details:
                return LUEResult(
                    mode=mode,
                    lue=lue,
                    avt=avt_val,
                    pce=pce,
                    avt_details=avt_result if isinstance(avt_result, AVTResult) else None
                )
            else:
                return lue
    
    def analyze_sample(
        self, 
        spectrum_file: str, 
        performance_file: str,
        sample_name: str = None
    ) -> FullAnalysisResult:
        """
        对单个样品进行完整分析
        
        参数：
            spectrum_file: 光谱文件路径（Abs 或 %T 格式）
            performance_file: 性能文件路径
            sample_name: 样品名称（可选）
            
        返回：
            FullAnalysisResult 对象，包含所有计算结果
        """
        # 解析样品名称
        if sample_name is None:
            sample_name = Path(spectrum_file).stem.replace('(UDS)', '').strip()
        
        # 加载光谱数据
        wavelengths, values, data_mode = parse_spectrum_file(spectrum_file)
        
        # 转换为透过率
        if data_mode == '%T':
            transmittance = values / 100.0
        else:
            transmittance = absorbance_to_transmittance(values, is_od_times_10=True)
        
        transmittance = np.clip(transmittance, 0, 1)
        
        # 解析性能数据
        performance = parse_performance_file(performance_file)
        pce = performance.get('PCE', 0)
        
        # 计算两种 LUE
        lue_results = self.calculate_from_spectrum(
            wavelengths, transmittance, pce, mode='both', return_details=True
        )
        
        # 设置样品名称
        lue_results['traditional'].sample_name = sample_name
        lue_results['plant'].sample_name = sample_name
        
        return FullAnalysisResult(
            sample_name=sample_name,
            lue_traditional=lue_results['traditional'],
            lue_plant=lue_results['plant'],
            performance=performance,
            wavelengths=wavelengths,
            transmittance=transmittance
        )
    
    def analyze_from_transmittance_file(
        self, 
        t_file: str, 
        performance_file: str,
        sample_name: str = None
    ) -> FullAnalysisResult:
        """
        专门从透过率文件进行分析（推荐使用此方法）
        
        参数：
            t_file: 透过率文件路径 (%T 格式)
            performance_file: 性能文件路径
            sample_name: 样品名称（可选）
            
        返回：
            FullAnalysisResult 对象
        """
        return self.analyze_sample(t_file, performance_file, sample_name)
    
    def batch_analyze(
        self, 
        spectrum_dir: str, 
        performance_dir: str,
        spectrum_type: str = 'auto'
    ) -> List[FullAnalysisResult]:
        """
        批量分析多个样品
        
        参数：
            spectrum_dir: 光谱文件目录
            performance_dir: 性能文件目录
            spectrum_type: 光谱类型 ('abs', 't', 或 'auto')
            
        返回：
            FullAnalysisResult 列表
        """
        matches = match_sample_files(spectrum_dir, performance_dir, spectrum_type)
        
        results = []
        for sample_name, spec_file, perf_file, _ in matches:
            try:
                result = self.analyze_sample(spec_file, perf_file, sample_name)
                results.append(result)
            except Exception as e:
                print(f"警告: 处理样品 {sample_name} 时出错: {e}")
        
        return results
    
    def generate_report(
        self, 
        result: FullAnalysisResult,
        output_file: str = None
    ) -> str:
        """
        生成详细的计算报告
        
        参数：
            result: FullAnalysisResult 对象
            output_file: 输出文件路径（可选）
            
        返回：
            报告文本
        """
        report_lines = [
            "=" * 70,
            f"LUE 计算报告",
            "=" * 70,
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"样品名称: {result.sample_name}",
            "",
            "-" * 70,
            "器件性能参数",
            "-" * 70,
        ]
        
        perf = result.performance
        if 'Jsc' in perf:
            report_lines.append(f"  短路电流密度 (Jsc):  {perf['Jsc']:.2f} mA/cm²")
        if 'Voc' in perf:
            report_lines.append(f"  开路电压 (Voc):      {perf['Voc']:.3f} V")
        if 'FF' in perf:
            report_lines.append(f"  填充因子 (FF):       {perf['FF']:.2f} %")
        if 'PCE' in perf:
            report_lines.append(f"  光电转换效率 (PCE):  {perf['PCE']:.2f} %")
        
        report_lines.extend([
            "",
            "-" * 70,
            "Traditional LUE (Human Eye Response)",
            "-" * 70,
            f"  Wavelength Range: {result.lue_traditional.avt_details.wavelength_range[0]}",
            f"                  - {result.lue_traditional.avt_details.wavelength_range[1]} nm",
            f"  Response Function: {result.lue_traditional.avt_details.response_function}",
            f"  Formula: {result.lue_traditional.avt_details.formula}",
            "",
            f"  AVT (Human):  {result.lue_traditional.avt:.2f} %",
            f"  PCE:          {result.lue_traditional.pce:.2f} %",
            "  " + "-" * 24,
            f"  LUE = AVT x PCE / 100 = {result.lue_traditional.lue:.4f} %",
            "",
            "-" * 70,
            "Plant LUE (Chlorophyll Response)",
            "-" * 70,
            f"  Wavelength Range: {result.lue_plant.avt_details.wavelength_range[0]}",
            f"                  - {result.lue_plant.avt_details.wavelength_range[1]} nm",
            f"  Response Function: {result.lue_plant.avt_details.response_function}",
            f"  Formula: {result.lue_plant.avt_details.formula}",
            "",
            f"  AVT (Plant):  {result.lue_plant.avt:.2f} %",
            f"  PCE:          {result.lue_plant.pce:.2f} %",
            "  " + "-" * 24,
            f"  LUE = AVT x PCE / 100 = {result.lue_plant.lue:.4f} %",
            "",
            "=" * 70,
            "Summary",
            "=" * 70,
            f"  LUE (Traditional): {result.lue_traditional.lue:.4f} %",
            f"  LUE (Plant):       {result.lue_plant.lue:.4f} %",
            "=" * 70,
        ])
        
        report = "\n".join(report_lines)
        
        if output_file:
            Path(output_file).parent.mkdir(parents=True, exist_ok=True)
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(report)
        
        return report
    
    def generate_summary_table(self, results: List[FullAnalysisResult]) -> str:
        """
        生成所有样品的汇总表格
        
        参数：
            results: FullAnalysisResult 列表
            
        返回：
            表格文本
        """
        lines = [
            "=" * 100,
            "LUE 计算结果汇总表",
            "=" * 100,
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"样品数量: {len(results)}",
            "",
            "-" * 100,
            f"{'样品名称':<20} {'PCE(%)':<10} {'AVT_H(%)':<12} {'AVT_P(%)':<12} "
            f"{'LUE_Trad(%)':<14} {'LUE_Plant(%)':<14}",
            "-" * 100,
        ]
        
        for r in results:
            lines.append(
                f"{r.sample_name:<20} "
                f"{r.performance.get('PCE', 0):<10.2f} "
                f"{r.lue_traditional.avt:<12.2f} "
                f"{r.lue_plant.avt:<12.2f} "
                f"{r.lue_traditional.lue:<14.4f} "
                f"{r.lue_plant.lue:<14.4f}"
            )
        
        lines.extend([
            "-" * 100,
            "",
            "说明:",
            "  AVT_H:    人眼响应平均可见光透过率 (380-780nm, CIE 1931 V(λ) 加权)",
            "  AVT_P:    植物响应平均透过率 (400-700nm, 叶绿素吸收光谱加权)",
            "  LUE_Trad: 传统光利用效率 = AVT_H × PCE / 100",
            "  LUE_Plant: 植物光利用效率 = AVT_P × PCE / 100",
            "=" * 100,
        ])
        
        return "\n".join(lines)


# ============================================================
# 便捷函数（保持向后兼容性）
# ============================================================

def calculate_lue(avt: float, pce: float) -> float:
    """计算 LUE 值（便捷函数）"""
    return avt * pce / 100.0


def calculate_all_lue(absorption_file: str, performance_file: str,
                      sample_name: str = None) -> Dict:
    """
    计算样品的所有 LUE 值（便捷函数，保持向后兼容）
    
    参数：
        absorption_file: 吸收谱/透过率文件路径
        performance_file: 性能文件路径
        sample_name: 样品名称
        
    返回：
        包含完整计算结果的字典
    """
    engine = LUEEngine()
    result = engine.analyze_sample(absorption_file, performance_file, sample_name)
    
    return {
        'sample_name': result.sample_name,
        'performance': result.performance,
        'avt_human': result.lue_traditional.avt,
        'avt_plant': result.lue_plant.avt,
        'lue_traditional': result.lue_traditional.lue,
        'lue_plant': result.lue_plant.lue,
        'wavelengths': result.wavelengths,
        'transmittance': result.transmittance,
    }


def generate_report(results: Dict, output_file: str = None) -> str:
    """生成报告（便捷函数，保持向后兼容）"""
    engine = LUEEngine()
    
    # 转换旧格式到新格式
    from .avt import AVTResult
    
    full_result = FullAnalysisResult(
        sample_name=results.get('sample_name', 'Unknown'),
        lue_traditional=LUEResult(
            mode='traditional',
            lue=results.get('lue_traditional', 0),
            avt=results.get('avt_human', 0),
            pce=results.get('performance', {}).get('PCE', 0),
            avt_details=AVTResult(
                mode='human',
                avt=results.get('avt_human', 0),
                wavelength_range=(380, 780),
                response_function='CIE 1931 V(λ) 人眼明视觉响应',
                formula='AVT = ∫T(λ)·S(λ)·V(λ)dλ / ∫S(λ)·V(λ)dλ'
            )
        ),
        lue_plant=LUEResult(
            mode='plant',
            lue=results.get('lue_plant', 0),
            avt=results.get('avt_plant', 0),
            pce=results.get('performance', {}).get('PCE', 0),
            avt_details=AVTResult(
                mode='plant',
                avt=results.get('avt_plant', 0),
                wavelength_range=(400, 700),
                response_function='叶绿素 a+b 吸收光谱',
                formula='AVT_plant = ∫T(λ)·S(λ)·Chl(λ)dλ / ∫S(λ)·Chl(λ)dλ'
            )
        ),
        performance=results.get('performance', {}),
        wavelengths=results.get('wavelengths'),
        transmittance=results.get('transmittance')
    )
    
    return engine.generate_report(full_result, output_file)


def generate_summary_table(all_results: List[Dict]) -> str:
    """生成汇总表格（便捷函数，保持向后兼容）"""
    engine = LUEEngine()
    
    # 转换旧格式到新格式
    from .avt import AVTResult
    
    full_results = []
    for r in all_results:
        full_results.append(FullAnalysisResult(
            sample_name=r.get('sample_name', 'Unknown'),
            lue_traditional=LUEResult(
                mode='traditional',
                lue=r.get('lue_traditional', 0),
                avt=r.get('avt_human', 0),
                pce=r.get('performance', {}).get('PCE', 0),
                avt_details=AVTResult(
                    mode='human', avt=r.get('avt_human', 0),
                    wavelength_range=(380, 780),
                    response_function='CIE 1931 V(λ)',
                    formula='AVT = ∫T(λ)·S(λ)·V(λ)dλ / ∫S(λ)·V(λ)dλ'
                )
            ),
            lue_plant=LUEResult(
                mode='plant',
                lue=r.get('lue_plant', 0),
                avt=r.get('avt_plant', 0),
                pce=r.get('performance', {}).get('PCE', 0),
                avt_details=AVTResult(
                    mode='plant', avt=r.get('avt_plant', 0),
                    wavelength_range=(400, 700),
                    response_function='叶绿素 a+b',
                    formula='AVT_plant = ∫T(λ)·S(λ)·Chl(λ)dλ / ∫S(λ)·Chl(λ)dλ'
                )
            ),
            performance=r.get('performance', {})
        ))
    
    return engine.generate_summary_table(full_results)
