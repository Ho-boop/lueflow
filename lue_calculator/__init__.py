# -*- coding: utf-8 -*-
"""
LUE计算器模块
用于计算半透明有机光伏器件的光利用效率（Light Utilization Efficiency）

支持两种LUE计算：
1. 传统LUE（人眼响应）：基于CIE 1931 V(λ)
2. 植物温室LUE：基于叶绿素吸收光谱

核心引擎：
- AVTEngine: AVT 测量引擎（支持人眼响应和植物响应两种模式）
- LUEEngine: LUE 测量引擎（支持传统和植物两种模式）
"""

# 数据解析
from .data_parser import (
    parse_spectrum_file,
    parse_absorption_spectrum, 
    parse_transmittance_spectrum,
    parse_performance_file,
    absorbance_to_transmittance,
    transmittance_to_absorbance,
    match_sample_files,
    match_abs_t_pairs,
    # 向后兼容
    absorption_to_transmittance
)

# 光谱数据
from .spectra import (
    get_am15g_spectrum, 
    get_photopic_response, 
    get_chlorophyll_response,
    interpolate_spectrum
)

# AVT 引擎和便捷函数
from .avt import (
    AVTEngine,
    AVTMode,
    AVTResult,
    calculate_avt_human, 
    calculate_avt_plant,
    calculate_both_avt
)

# LUE 引擎和便捷函数
from .lue import (
    LUEEngine,
    LUEMode,
    LUEResult,
    FullAnalysisResult,
    calculate_lue, 
    calculate_all_lue, 
    generate_report,
    generate_summary_table
)

__version__ = '0.1.0'
__all__ = [
    # 引擎类
    'AVTEngine',
    'LUEEngine',
    
    # 数据类
    'AVTMode',
    'AVTResult',
    'LUEMode',
    'LUEResult',
    'FullAnalysisResult',
    
    # 数据解析
    'parse_spectrum_file',
    'parse_absorption_spectrum',
    'parse_transmittance_spectrum',
    'parse_performance_file',
    'absorbance_to_transmittance',
    'transmittance_to_absorbance',
    'absorption_to_transmittance',
    'match_sample_files',
    'match_abs_t_pairs',
    
    # 光谱数据
    'get_am15g_spectrum',
    'get_photopic_response',
    'get_chlorophyll_response',
    'interpolate_spectrum',
    
    # AVT 便捷函数
    'calculate_avt_human',
    'calculate_avt_plant',
    'calculate_both_avt',
    
    # LUE 便捷函数
    'calculate_lue',
    'calculate_all_lue',
    'generate_report',
    'generate_summary_table',
]
