# -*- coding: utf-8 -*-
"""
AVT 测量引擎（平均可见光透过率）

提供两种 AVT 计算模式：
1. 人眼响应 AVT (AVT_Human)：使用 CIE 1931 V(λ) 人眼明视觉响应函数加权
2. 植物响应 AVT (AVT_Plant)：使用叶绿素吸收光谱加权，用于植物温室应用

核心公式：
    AVT = ∫T(λ)·S(λ)·W(λ)dλ / ∫S(λ)·W(λ)dλ
    
其中：
    - T(λ)：透过率光谱
    - S(λ)：AM1.5G 太阳光谱
    - W(λ)：加权函数（人眼响应或叶绿素吸收）
"""

import numpy as np
from scipy.integrate import trapezoid
from typing import Dict, Optional, Tuple, Union
from dataclasses import dataclass
from enum import Enum

from .spectra import (
    get_am15g_spectrum, 
    get_photopic_response, 
    get_chlorophyll_response,
    interpolate_spectrum
)
from .data_parser import (
    parse_spectrum_file,
    parse_transmittance_spectrum,
    parse_absorption_spectrum,
    absorbance_to_transmittance
)


class AVTMode(Enum):
    """AVT 计算模式"""
    HUMAN = "human"      # 人眼响应
    PLANT = "plant"      # 植物响应
    BOTH = "both"        # 同时计算两种


@dataclass
class AVTResult:
    """AVT 计算结果"""
    mode: str                       # 计算模式 ('human' 或 'plant')
    avt: float                      # AVT 值（百分比）
    wavelength_range: Tuple[int, int]  # 波长范围
    response_function: str          # 使用的响应函数名称
    formula: str                    # 使用的公式
    numerator: float = None         # 分子积分值
    denominator: float = None       # 分母积分值
    
    def __str__(self) -> str:
        return f"AVT ({self.mode}): {self.avt:.2f}% [{self.wavelength_range[0]}-{self.wavelength_range[1]}nm]"


class AVTEngine:
    """
    AVT 测量引擎
    
    用法示例：
        # 方式1：从透过率数组计算
        engine = AVTEngine()
        result = engine.calculate(wavelengths, transmittance, mode='human')
        
        # 方式2：从文件计算
        result = engine.calculate_from_file('path/to/t_file.txt')
        
        # 方式3：同时计算两种模式
        results = engine.calculate_both(wavelengths, transmittance)
    """
    
    # 波长范围定义
    VISIBLE_RANGE = (380, 780)      # 可见光范围（人眼响应）
    PAR_RANGE = (400, 700)          # 光合有效辐射范围（植物响应）
    
    def __init__(self, use_am15g: bool = True):
        """
        初始化 AVT 引擎
        
        参数：
            use_am15g: 是否使用 AM1.5G 太阳光谱加权 (默认 True)
        """
        self.use_am15g = use_am15g
    
    def calculate(
        self, 
        wavelengths: np.ndarray, 
        transmittance: np.ndarray,
        mode: Union[str, AVTMode] = 'human',
        return_details: bool = False
    ) -> Union[float, AVTResult]:
        """
        计算 AVT（平均可见光透过率）
        
        参数：
            wavelengths: 波长数组 (nm)
            transmittance: 透过率数组 (0-1 范围)
            mode: 计算模式 ('human' 或 'plant')
            return_details: 是否返回详细结果
            
        返回：
            AVT 值（百分比）或 AVTResult 对象
        """
        if isinstance(mode, AVTMode):
            mode = mode.value
        
        if mode == 'human':
            return self._calculate_human(wavelengths, transmittance, return_details)
        elif mode == 'plant':
            return self._calculate_plant(wavelengths, transmittance, return_details)
        else:
            raise ValueError(f"未知的计算模式: {mode}，请使用 'human' 或 'plant'")
    
    def calculate_both(
        self, 
        wavelengths: np.ndarray, 
        transmittance: np.ndarray,
        return_details: bool = False
    ) -> Dict[str, Union[float, AVTResult]]:
        """
        同时计算人眼响应和植物响应的 AVT
        
        参数：
            wavelengths: 波长数组 (nm)
            transmittance: 透过率数组 (0-1 范围)
            return_details: 是否返回详细结果
            
        返回：
            包含两种 AVT 结果的字典 {'human': ..., 'plant': ...}
        """
        return {
            'human': self._calculate_human(wavelengths, transmittance, return_details),
            'plant': self._calculate_plant(wavelengths, transmittance, return_details)
        }
    
    def calculate_from_file(
        self, 
        file_path: str,
        mode: Union[str, AVTMode] = 'human',
        return_details: bool = False
    ) -> Union[float, AVTResult]:
        """
        从光谱文件计算 AVT
        
        自动识别文件类型 (Abs 或 %T) 并进行相应处理
        
        参数：
            file_path: 光谱文件路径
            mode: 计算模式 ('human' 或 'plant')
            return_details: 是否返回详细结果
            
        返回：
            AVT 值（百分比）或 AVTResult 对象
        """
        wavelengths, transmittance = self._load_transmittance_from_file(file_path)
        return self.calculate(wavelengths, transmittance, mode, return_details)
    
    def calculate_both_from_file(
        self, 
        file_path: str,
        return_details: bool = False
    ) -> Dict[str, Union[float, AVTResult]]:
        """
        从光谱文件计算两种 AVT
        
        参数：
            file_path: 光谱文件路径
            return_details: 是否返回详细结果
            
        返回：
            包含两种 AVT 结果的字典
        """
        wavelengths, transmittance = self._load_transmittance_from_file(file_path)
        return self.calculate_both(wavelengths, transmittance, return_details)
    
    def _load_transmittance_from_file(self, file_path: str) -> Tuple[np.ndarray, np.ndarray]:
        """从文件加载透过率数据"""
        wavelengths, values, data_mode = parse_spectrum_file(file_path)
        
        if data_mode == '%T':
            # 直接是透过率百分比，转换为 0-1
            transmittance = values / 100.0
        else:
            # 是吸光度 (OD×10 格式)，需要转换
            transmittance = absorbance_to_transmittance(values, is_od_times_10=True)
        
        # 确保在有效范围
        transmittance = np.clip(transmittance, 0, 1)
        
        return wavelengths, transmittance
    
    def _calculate_human(
        self, 
        wavelengths: np.ndarray, 
        transmittance: np.ndarray,
        return_details: bool = False
    ) -> Union[float, AVTResult]:
        """计算人眼响应 AVT"""
        wl_min, wl_max = self.VISIBLE_RANGE
        
        # 创建统一的波长网格（1nm 间隔）
        wl_grid = np.arange(wl_min, wl_max + 1, 1)
        
        # 将所有光谱数据插值到统一网格
        T_interp = interpolate_spectrum(wavelengths, transmittance, wl_grid)
        _, V_interp = get_photopic_response(wl_grid)
        
        if self.use_am15g:
            _, S_interp = get_am15g_spectrum(wl_grid)
            numerator = trapezoid(T_interp * S_interp * V_interp, wl_grid)
            denominator = trapezoid(S_interp * V_interp, wl_grid)
            formula = 'AVT = ∫T(λ)·S(λ)·V(λ)dλ / ∫S(λ)·V(λ)dλ'
        else:
            numerator = trapezoid(T_interp * V_interp, wl_grid)
            denominator = trapezoid(V_interp, wl_grid)
            formula = 'AVT = ∫T(λ)·V(λ)dλ / ∫V(λ)dλ'
        
        # 计算 AVT（转换为百分比）
        avt = (numerator / denominator) * 100 if denominator > 0 else 0
        
        if return_details:
            return AVTResult(
                mode='human',
                avt=avt,
                wavelength_range=(wl_min, wl_max),
                response_function='CIE 1931 V(λ) 人眼明视觉响应',
                formula=formula,
                numerator=numerator,
                denominator=denominator
            )
        
        return avt
    
    def _calculate_plant(
        self, 
        wavelengths: np.ndarray, 
        transmittance: np.ndarray,
        return_details: bool = False
    ) -> Union[float, AVTResult]:
        """计算植物响应 AVT"""
        wl_min, wl_max = self.PAR_RANGE
        
        # 创建统一的波长网格（1nm 间隔）
        wl_grid = np.arange(wl_min, wl_max + 1, 1)
        
        # 将所有光谱数据插值到统一网格
        T_interp = interpolate_spectrum(wavelengths, transmittance, wl_grid)
        _, Chl_interp = get_chlorophyll_response(wl_grid)
        
        if self.use_am15g:
            _, S_interp = get_am15g_spectrum(wl_grid)
            numerator = trapezoid(T_interp * S_interp * Chl_interp, wl_grid)
            denominator = trapezoid(S_interp * Chl_interp, wl_grid)
            formula = 'AVT_plant = ∫T(λ)·S(λ)·Chl(λ)dλ / ∫S(λ)·Chl(λ)dλ'
        else:
            numerator = trapezoid(T_interp * Chl_interp, wl_grid)
            denominator = trapezoid(Chl_interp, wl_grid)
            formula = 'AVT_plant = ∫T(λ)·Chl(λ)dλ / ∫Chl(λ)dλ'
        
        # 计算 AVT（转换为百分比）
        avt = (numerator / denominator) * 100 if denominator > 0 else 0
        
        if return_details:
            return AVTResult(
                mode='plant',
                avt=avt,
                wavelength_range=(wl_min, wl_max),
                response_function='叶绿素 a+b 吸收光谱',
                formula=formula,
                numerator=numerator,
                denominator=denominator
            )
        
        return avt


# ============================================================
# 便捷函数（保持向后兼容性）
# ============================================================

def calculate_avt_human(wavelengths: np.ndarray, transmittance: np.ndarray,
                        return_details: bool = False):
    """计算人眼响应的 AVT（便捷函数）"""
    engine = AVTEngine()
    return engine.calculate(wavelengths, transmittance, 'human', return_details)


def calculate_avt_plant(wavelengths: np.ndarray, transmittance: np.ndarray,
                        return_details: bool = False):
    """计算植物响应的 AVT（便捷函数）"""
    engine = AVTEngine()
    return engine.calculate(wavelengths, transmittance, 'plant', return_details)


def calculate_both_avt(wavelengths: np.ndarray, absorption: np.ndarray,
                       return_details: bool = False) -> Dict:
    """
    同时计算人眼响应和植物响应的 AVT（便捷函数）
    
    注意：此函数接受吸光度数组（OD×10 格式），会自动转换为透过率
    """
    # 转换为透过率
    transmittance = absorbance_to_transmittance(absorption, is_od_times_10=True)
    
    engine = AVTEngine()
    results = engine.calculate_both(wavelengths, transmittance, return_details)
    results['transmittance'] = transmittance
    
    return results
