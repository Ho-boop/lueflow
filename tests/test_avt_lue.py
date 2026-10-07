# -*- coding: utf-8 -*-
"""
AVT / LUE 计算引擎测试

思路：不做「跑通即通过」的冒烟测试，而是用三类可独立验证的基准约束计算结果
1. 解析解：均匀透过率下加权平均必须等于该常数，与权重函数无关
2. 权威数据：内置的 CIE 1931 V(λ) 必须与标准值逐点一致
3. 物理边界：AVT 落在 0-100%，全透 = 100%，全不透 = 0%
"""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lue_calculator.avt import AVTEngine  # noqa: E402
from lue_calculator.lue import LUEEngine  # noqa: E402
from lue_calculator.spectra import (  # noqa: E402
    PHOTOPIC_WAVELENGTHS,
    PHOTOPIC_RESPONSE,
    get_am15g_spectrum,
    interpolate_spectrum,
)



WL = np.arange(300, 901, 2.0)


# ---------------------------------------------------------------- 解析解

@pytest.mark.parametrize("level", [0.0, 0.25, 0.5, 0.732, 1.0])
@pytest.mark.parametrize("mode", ["human", "plant"])
def test_uniform_transmittance_equals_its_own_mean(level, mode):
    """
    加权平均的定义性质：若 T(λ) ≡ c，则无论权重 S(λ)·W(λ) 长什么样，
    AVT = ∫c·S·W dλ / ∫S·W dλ = c。

    这条能一次性抓出分子分母权重不一致、归一化漏乘、积分区间错配等错误。
    """
    engine = AVTEngine()
    avt = engine.calculate(WL, np.full_like(WL, level), mode=mode)
    assert avt == pytest.approx(level * 100, abs=1e-9)


def test_am15g_weighting_changes_result_for_nonuniform_spectrum():
    """
    对非均匀透过率，开/关 AM1.5G 加权必须给出不同结果 —— 否则说明 use_am15g 开关没生效。
    """
    # 蓝端低透、红端高透的斜坡
    t = np.clip((WL - 400) / 400, 0, 1)
    with_sun = AVTEngine(use_am15g=True).calculate(WL, t, "human")
    without_sun = AVTEngine(use_am15g=False).calculate(WL, t, "human")
    assert abs(with_sun - without_sun) > 0.1


# ---------------------------------------------------------------- 权威数据

# CIE 1931 2° 明视觉光效函数 V(λ) 标准值（抽样校验点）
CIE_1931_REFERENCE = {
    380: 0.000039, 400: 0.000396, 450: 0.038000, 500: 0.323000,
    530: 0.862000, 555: 1.000000, 560: 0.995000, 600: 0.631000,
    650: 0.107000, 700: 0.004102, 750: 0.000120,
}


@pytest.mark.parametrize("wl,expected", sorted(CIE_1931_REFERENCE.items()))
def test_photopic_table_matches_cie_1931_standard(wl, expected):
    """内置人眼响应曲线必须是真正的 CIE 1931 标准值，而非手工近似。"""
    idx = int(np.where(PHOTOPIC_WAVELENGTHS == wl)[0][0])
    assert PHOTOPIC_RESPONSE[idx] == pytest.approx(expected, abs=6e-6)


def test_photopic_peak_is_normalized_at_555nm():
    """V(λ) 按定义在 555nm 处归一化为 1.0，且为全局最大。"""
    peak_idx = int(np.argmax(PHOTOPIC_RESPONSE))
    assert PHOTOPIC_WAVELENGTHS[peak_idx] == 555
    assert PHOTOPIC_RESPONSE[peak_idx] == pytest.approx(1.0)


def test_am15g_irradiance_is_physically_plausible():
    """AM1.5G 可见光波段辐照度量级应在 0.4-2.0 W/m²/nm。"""
    _, irr = get_am15g_spectrum(np.arange(380, 781, 5))
    assert irr.min() > 0.4
    assert irr.max() < 2.0


# ---------------------------------------------------------------- 物理边界

def test_avt_bounds_and_extremes():
    engine = AVTEngine()
    assert engine.calculate(WL, np.ones_like(WL), "human") == pytest.approx(100.0)
    assert engine.calculate(WL, np.zeros_like(WL), "human") == pytest.approx(0.0)


def test_avt_is_monotonic_in_transmittance():
    """整体抬高透过率，AVT 必须单调上升。"""
    engine = AVTEngine()
    base = np.full_like(WL, 0.3)
    prev = -1.0
    for delta in [0.0, 0.1, 0.2, 0.3]:
        avt = engine.calculate(WL, base + delta, "human")
        assert avt > prev
        prev = avt


def test_human_and_plant_use_different_wavelength_windows():
    """
    人眼 AVT 取 380-780nm，植物 AVT 取 PAR 400-700nm。

    构造一个只在 700nm 以上透光的样品：
    - 植物模式：完全落在 PAR 窗口之外，必须严格为 0
    - 人眼模式：仍有响应，但因 V(λ) 在红端已衰减到 1e-3 量级，
      数值本身很小（约 0.04%），所以这里只断言「显著大于 0」而非某个大阈值

    注意用 `> 700` 而非 `>= 700`：PAR 积分区间 400-700nm 是闭区间，
    端点 700nm 若取 1 会在梯形积分中贡献一个非零边界项。
    """
    t = np.where(WL > 700, 1.0, 0.0)
    engine = AVTEngine()
    assert engine.calculate(WL, t, "human") > 1e-3
    assert engine.calculate(WL, t, "plant") == pytest.approx(0.0, abs=1e-6)


def test_interpolation_does_not_extrapolate_out_of_range():
    """插值到仪器扫描范围之外时不应产生负值或 >1 的非物理透过率。"""
    coarse_wl = np.array([400.0, 500.0, 600.0, 700.0])
    coarse_t = np.array([0.2, 0.6, 0.5, 0.3])
    grid = np.arange(380, 781, 1)
    out = interpolate_spectrum(coarse_wl, coarse_t, grid)
    assert np.all(out >= 0) and np.all(out <= 1)


# ---------------------------------------------------------------- LUE

@pytest.mark.parametrize(
    "avt,pce,expected",
    [(50.0, 10.0, 5.0), (0.0, 12.0, 0.0), (100.0, 8.0, 8.0), (59.24, 4.76, 2.8198)],
)
def test_lue_definition(avt, pce, expected):
    """LUE = AVT × PCE，两者皆为百分数故需除以 100。"""
    assert LUEEngine().calculate(avt, pce) == pytest.approx(expected, abs=1e-3)


def test_lue_never_exceeds_pce():
    """AVT ≤ 100%，因此 LUE 恒不大于 PCE —— 一个廉价但有效的量纲哨兵。"""
    engine = LUEEngine()
    for avt in [0, 25, 59.2, 100]:
        assert engine.calculate(avt, 12.0) <= 12.0 + 1e-9
