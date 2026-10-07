# -*- coding: utf-8 -*-
"""
数据解析模块
用于解析日立U-3900H分光光度计的吸收谱文件、透过率文件和器件性能文件

支持的数据类型:
1. Abs 文件 (吸光度模式) - 数据格式为 OD×10
2. %T 文件 (透过率模式) - 数据为透过率百分比
3. 性能参数文件 - 包含 Jsc, Voc, FF, PCE 等
"""

import re
import numpy as np
from pathlib import Path
from typing import Tuple, Dict, Optional, Literal


def parse_spectrum_file(file_path: str) -> Tuple[np.ndarray, np.ndarray, str]:
    """
    自动识别并解析日立U-3900H分光光度计导出的光谱TXT文件
    
    自动检测文件类型 (Abs 或 %T) 并返回相应数据
    
    参数:
        file_path: 光谱文件路径
        
    返回:
        (wavelengths, data, data_mode): 波长数组(nm)、数据数组、数据模式('Abs'或'%T')
    """
    wavelengths = []
    values = []
    data_mode = None
    
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
    
    # 首先识别数据模式
    for line in lines:
        if 'Data Mode:' in line:
            if '%T' in line:
                data_mode = '%T'
            elif 'Abs' in line:
                data_mode = 'Abs'
            break
    
    # 如果没找到 Data Mode 标记，使用默认值
    if data_mode is None:
        # 检查文件路径中的线索
        file_path_lower = file_path.lower()
        if '/t/' in file_path_lower or '\\t\\' in file_path_lower or '_t_' in file_path_lower:
            data_mode = '%T'
        else:
            data_mode = 'Abs'
    
    # 定位数据区起点
    #
    # 【为什么不能只靠正则识别数据行】
    # U-3900H 导出文件在 "Data Points" 之前还有一段 "Peaks" 峰识别表，形如：
    #     Peak #  Start(nm)  Apex(nm)  End(nm)  Height(%T)  Valley(nm)  Valley(%T)
    #     1       894.00     816.00    656.00   23.3        656.00      45.7
    #     2       656.00     636.00    422.00   44.8        422.00      77.5
    # 这两行同样满足 "数字 + 空白 + 数字" 的形式，旧逻辑会把它们当成数据点，
    # 于是凭空多出 (λ=1, 894) 和 (λ=2, 656) 两个伪数据点。
    # 这两点落在 380-780nm 积分区间之外，对 AVT 结果无影响（实测偏差 0.000000%），
    # 但会污染点数统计、波长范围和采样间隔的判断，属于必须消除的隐患。
    #
    # 正确做法：以 "Data Points" 段落标记为准，仅解析其后的内容。
    data_start_idx = None
    for idx, line in enumerate(lines):
        if line.strip().lower().startswith('data points'):
            data_start_idx = idx + 1
            break

    if data_start_idx is not None:
        # 有明确段落标记：只解析该段之后的行
        candidate_lines = lines[data_start_idx:]
    else:
        # 兼容无 "Data Points" 标记的文件：退回启发式，但显式跳过 Peaks 表
        candidate_lines = []
        in_peaks_block = False
        started = False
        for line in lines:
            stripped = line.strip()
            if stripped.lower().startswith('peak'):
                in_peaks_block = True
                continue
            if in_peaks_block:
                # Peaks 表以空行结束
                if not stripped:
                    in_peaks_block = False
                continue
            if re.match(r'^\d+\.?\d*\s+[\-]?\d+\.?\d*', stripped):
                started = True
            if started:
                candidate_lines.append(line)

    for line in candidate_lines:
        line = line.strip()

        # 跳过空行与列名行（如 "nm\t%T"）
        if not line:
            continue

        # 解析数据行: "波长\t值" 或 "波长 值"
        parts = re.split(r'\s+', line)
        if len(parts) >= 2:
            try:
                wl = float(parts[0])
                val = float(parts[1])
                wavelengths.append(wl)
                values.append(val)
            except ValueError:
                continue
    
    # 转换为 numpy 数组
    wavelengths = np.array(wavelengths)
    values = np.array(values)
    
    # 按波长升序排列
    if len(wavelengths) > 0:
        sort_idx = np.argsort(wavelengths)
        wavelengths = wavelengths[sort_idx]
        values = values[sort_idx]
    
    return wavelengths, values, data_mode


def parse_transmittance_spectrum(file_path: str) -> Tuple[np.ndarray, np.ndarray]:
    """
    解析日立U-3900H分光光度计导出的透过率(%T)文件
    
    参数:
        file_path: 透过率文件路径
        
    返回:
        (wavelengths, transmittance): 波长数组(nm)和透过率数组(0-1范围)
    """
    wavelengths, values, data_mode = parse_spectrum_file(file_path)
    
    if data_mode != '%T':
        print(f"警告: 文件 {file_path} 似乎不是透过率模式，但仍按透过率处理")
    
    # 将百分比转换为小数 (0-1)
    transmittance = values / 100.0
    # 限制在有效范围
    transmittance = np.clip(transmittance, 0, 1)
    
    return wavelengths, transmittance


def parse_absorption_spectrum(file_path: str) -> Tuple[np.ndarray, np.ndarray]:
    """
    解析日立U-3900H分光光度计导出的吸收谱(Abs)TXT文件
    
    参数:
        file_path: 吸收谱文件路径
        
    返回:
        (wavelengths, absorption): 波长数组(nm)和吸光度数组(OD×10格式)
    """
    wavelengths, values, data_mode = parse_spectrum_file(file_path)
    
    if data_mode != 'Abs':
        print(f"警告: 文件 {file_path} 似乎不是吸光度模式，但仍按吸光度处理")
    
    return wavelengths, values


def parse_performance_file(file_path: str) -> Dict[str, float]:
    """
    解析器件性能参数文件
    
    参数:
        file_path: 性能文件路径
        
    返回:
        包含jsc, voc, ff, pce等参数的字典（小写key）
        voc单位为V（从mV转换）
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        with open(file_path, 'r', encoding='gbk') as f:
            lines = f.readlines()
    
    if len(lines) < 3:
        raise ValueError(f"性能文件格式错误: {file_path}")
    
    # 第一行是列名（只去掉行尾空白）
    headers = lines[0].rstrip('\r\n').split('\t')
    # 第三行是数据（第二行是单位）
    # 注意：不能使用 strip()，因为数据行开头可能有空的Tab字段
    # 如果使用 strip() 会去掉开头的空白，导致列名与值的对应错位
    values = lines[2].rstrip('\r\n').split('\t')
    
    # 创建列名到值的映射
    data_map = {}
    for i, header in enumerate(headers):
        if i < len(values):
            data_map[header] = values[i]
    
    # 提取数据
    jsc = float(data_map.get('Jsc', 0))
    voc_mv = float(data_map.get('Voc', 0))  # 原始单位: mV
    voc_v = voc_mv / 1000  # 转换为V
    ff = float(data_map.get('FF', 0))
    pce = float(data_map.get('Eta', 0))  # Eta就是PCE
    
    return {
        'jsc': round(jsc, 2),
        'voc': round(voc_v, 3),  # Voc保留三位小数，单位V
        'ff': round(ff, 2),
        'pce': round(pce, 2)
    }


def absorbance_to_transmittance(absorbance: np.ndarray, is_od_times_10: bool = True) -> np.ndarray:
    """
    将吸光度转换为透过率
    
    参数:
        absorbance: 吸光度数组
        is_od_times_10: 是否是 OD×10 格式 (日立 U-3900H 导出格式)
                        True: 数据值3表示OD=0.3
                        False: 数据值0.3表示OD=0.3
        
    返回:
        透过率数组（0-1范围）
    
    公式: T = 10^(-OD)
    """
    if is_od_times_10:
        # 日立 U-3900H 的 OD×10 格式
        od = absorbance / 10.0
    else:
        od = absorbance
    
    # 限制OD在合理范围内（0-4，对应透过率100%-0.01%）
    od = np.clip(od, 0, 4)
    # 计算透过率
    transmittance = np.power(10, -od)
    return transmittance


def transmittance_to_absorbance(transmittance: np.ndarray, output_od_times_10: bool = False) -> np.ndarray:
    """
    将透过率转换为吸光度
    
    参数:
        transmittance: 透过率数组（0-1范围）
        output_od_times_10: 是否输出 OD×10 格式
        
    返回:
        吸光度数组
    
    公式: OD = -log10(T)
    """
    # 限制透过率在有效范围，避免 log(0)
    transmittance = np.clip(transmittance, 0.0001, 1)
    od = -np.log10(transmittance)
    
    if output_od_times_10:
        return od * 10.0
    return od


# 保持向后兼容性
def absorption_to_transmittance(absorption: np.ndarray) -> np.ndarray:
    """
    将吸光度（OD×10格式）转换为透过率
    
    这是旧版本函数，保持向后兼容性
    建议使用新的 absorbance_to_transmittance 函数
    """
    return absorbance_to_transmittance(absorption, is_od_times_10=True)


def match_sample_files(spectrum_dir: str, performance_dir: str, 
                       spectrum_type: Literal['abs', 't', 'auto'] = 'auto') -> list:
    """
    匹配光谱文件和性能文件
    
    参数:
        spectrum_dir: 光谱文件目录（可以是 abs 或 t 子目录）
        performance_dir: 性能文件目录
        spectrum_type: 光谱类型 ('abs', 't', 或 'auto' 自动检测)
        
    返回:
        匹配的文件对列表 [(sample_name, spectrum_file, perf_file, spectrum_type), ...]
    """
    spec_path = Path(spectrum_dir)
    perf_path = Path(performance_dir)
    
    matches = []
    
    # 获取所有性能文件
    perf_files = {}
    for f in perf_path.glob('*.txt'):
        perf_files[f.stem] = f
    
    # 查找匹配的光谱文件
    for perf_name, perf_file in perf_files.items():
        # 尝试匹配不同格式的光谱文件名
        possible_names = [
            f"{perf_name}(UDS).TXT",
            f"{perf_name}.TXT",
            f"{perf_name}(UDS).txt",
            f"{perf_name}.txt",
        ]
        
        for spec_name in possible_names:
            spec_file = spec_path / spec_name
            if spec_file.exists():
                # 检测文件类型
                detected_type = spectrum_type
                if spectrum_type == 'auto':
                    _, _, mode = parse_spectrum_file(str(spec_file))
                    detected_type = 't' if mode == '%T' else 'abs'
                
                matches.append((perf_name, str(spec_file), str(perf_file), detected_type))
                break
    
    return matches


def match_abs_t_pairs(base_dir: str, performance_dir: str) -> list:
    """
    匹配 abs 和 t 文件对以及性能文件
    
    参数:
        base_dir: 包含 abs 和 t 子目录的基础目录
        performance_dir: 性能文件目录
        
    返回:
        匹配的文件组列表 [(sample_name, abs_file, t_file, perf_file), ...]
    """
    base_path = Path(base_dir)
    abs_path = base_path / 'abs'
    t_path = base_path / 't'
    perf_path = Path(performance_dir)
    
    if not abs_path.exists() or not t_path.exists():
        print(f"警告: 找不到 abs 或 t 子目录在 {base_dir}")
        return []
    
    matches = []
    
    # 获取所有性能文件
    perf_files = {f.stem: f for f in perf_path.glob('*.txt')}
    
    # 获取所有 abs 文件
    abs_files = {}
    for f in abs_path.glob('*.TXT'):
        # 提取样品名（去掉 (UDS) 后缀）
        name = f.stem.replace('(UDS)', '').strip()
        abs_files[name] = f
    for f in abs_path.glob('*.txt'):
        name = f.stem.replace('(UDS)', '').strip()
        if name not in abs_files:
            abs_files[name] = f
    
    # 获取所有 t 文件
    t_files = {}
    for f in t_path.glob('*.TXT'):
        name = f.stem.replace('(UDS)', '').strip()
        t_files[name] = f
    for f in t_path.glob('*.txt'):
        name = f.stem.replace('(UDS)', '').strip()
        if name not in t_files:
            t_files[name] = f
    
    # 匹配所有三种文件
    for name in abs_files:
        if name in t_files:
            # 尝试匹配性能文件
            perf_file = None
            for pname, pfile in perf_files.items():
                if name in pname or pname in name:
                    perf_file = str(pfile)
                    break
            
            matches.append((
                name,
                str(abs_files[name]),
                str(t_files[name]),
                perf_file
            ))
    
    return matches
