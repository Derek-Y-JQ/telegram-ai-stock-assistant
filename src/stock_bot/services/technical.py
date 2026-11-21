"""Quantitative technical analysis engine with bilingual (EN/ZH) output."""

from __future__ import annotations

import numpy as np
import pandas as pd

from stock_bot.models import Lang, TechnicalReport, TechnicalSignal


class TechnicalAnalyzer:
    """Computes multi-indicator technical diagnosis from an OHLCV DataFrame."""

    @staticmethod
    def analyze(code: str, name: str, df: pd.DataFrame, lang: Lang = "en") -> TechnicalReport:
        if df.empty or len(df) < 20:
            msg = (
                "Insufficient historical data (at least 20 trading days required)."
                if lang == "en"
                else "历史行情数据不足（至少需要 20 个交易日）以进行技术面诊断。"
            )
            raise ValueError(msg)

        data = df.copy().sort_index()
        close = data["Close"].astype(float)
        high = data["High"].astype(float)
        low = data["Low"].astype(float)

        ma5 = close.rolling(5).mean()
        ma10 = close.rolling(10).mean()
        ma20 = close.rolling(20).mean()
        ma60 = close.rolling(60).mean() if len(close) >= 60 else pd.Series(np.nan, index=close.index)

        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        dif = ema12 - ema26
        dea = dif.ewm(span=9, adjust=False).mean()
        macd_hist = (dif - dea) * 2.0

        delta = close.diff()
        gain = delta.clip(lower=0.0)
        loss = (-delta).clip(lower=0.0)
        avg_gain = gain.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi14 = (100.0 - (100.0 / (1.0 + rs))).fillna(100.0)

        boll_mid = ma20
        boll_std = close.rolling(20).std()
        boll_upper = boll_mid + 2.0 * boll_std
        boll_lower = boll_mid - 2.0 * boll_std

        low_9 = low.rolling(9, min_periods=1).min()
        high_9 = high.rolling(9, min_periods=1).max()
        rsv = ((close - low_9) / (high_9 - low_9).replace(0, np.nan) * 100.0).fillna(50.0)
        kdj_k = rsv.ewm(alpha=1 / 3, adjust=False).mean()
        kdj_d = kdj_k.ewm(alpha=1 / 3, adjust=False).mean()
        kdj_j = 3.0 * kdj_k - 2.0 * kdj_d

        prev_close = close.shift(1)
        tr = pd.concat(
            [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
            axis=1,
        ).max(axis=1)
        atr14 = tr.rolling(14).mean()
        returns = close.pct_change()
        vol_20d = returns.rolling(20).std().iloc[-1] * np.sqrt(252) * 100.0

        recent_20 = data.tail(20)
        support = float(recent_20["Low"].min())
        resistance = float(recent_20["High"].max())

        latest_close = float(close.iloc[-1])
        trade_date = data.index[-1].strftime("%Y-%m-%d")

        def _val(series: pd.Series) -> float | None:
            v = series.iloc[-1]
            return None if pd.isna(v) else round(float(v), 2)

        v_ma5, v_ma10, v_ma20, v_ma60 = _val(ma5), _val(ma10), _val(ma20), _val(ma60)
        v_dif, v_dea, v_hist = _val(dif), _val(dea), _val(macd_hist)
        v_rsi = _val(rsi14)
        v_upper, v_mid, v_lower = _val(boll_upper), _val(boll_mid), _val(boll_lower)
        v_k, v_d, v_j = _val(kdj_k), _val(kdj_d), _val(kdj_j)
        v_atr = _val(atr14)
        v_vol = None if pd.isna(vol_20d) else round(float(vol_20d), 2)

        en = lang == "en"
        score = 50
        signals: list[TechnicalSignal] = []

        # 1. Moving Averages
        if v_ma5 and v_ma10 and v_ma20:
            ma_label = "Moving Averages" if en else "均线系统"
            if latest_close > v_ma5 > v_ma10 > v_ma20:
                score += 18
                signals.append(
                    TechnicalSignal(
                        name=ma_label,
                        status="bullish",
                        detail="Price above MA5/MA10/MA20 in bullish alignment" if en else "价格站上 MA5/MA10/MA20 且呈多头排列",
                    )
                )
            elif latest_close < v_ma5 < v_ma10 < v_ma20:
                score -= 18
                signals.append(
                    TechnicalSignal(
                        name=ma_label,
                        status="bearish",
                        detail="Price below MA5/MA10/MA20 in bearish alignment" if en else "价格跌破 MA5/MA10/MA20 且呈空头排列",
                    )
                )
            elif latest_close > v_ma20:
                score += 6
                signals.append(
                    TechnicalSignal(
                        name=ma_label,
                        status="bullish",
                        detail="Trading above 20-day MA; medium-term trend constructive" if en else "价格运行在 20 日生命线上方，中期偏强",
                    )
                )
            else:
                score -= 6
                signals.append(
                    TechnicalSignal(
                        name=ma_label,
                        status="bearish",
                        detail="Trading below 20-day MA; medium-term trend pressured" if en else "价格承压于 20 日均线下方，中期偏弱",
                    )
                )

        # 2. MACD
        if v_dif is not None and v_dea is not None and len(dif) >= 2:
            prev_diff = float(dif.iloc[-2] - dea.iloc[-2])
            curr_diff = float(dif.iloc[-1] - dea.iloc[-1])
            if prev_diff <= 0 < curr_diff:
                score += 15
                signals.append(
                    TechnicalSignal(
                        name="MACD",
                        status="bullish",
                        detail="Fresh bullish crossover (golden cross)" if en else "刚出现金叉信号，动能转强",
                    )
                )
            elif prev_diff >= 0 > curr_diff:
                score -= 15
                signals.append(
                    TechnicalSignal(
                        name="MACD",
                        status="bearish",
                        detail="Fresh bearish crossover (death cross)" if en else "刚出现死叉信号，动能转弱",
                    )
                )
            elif curr_diff > 0:
                score += 8
                signals.append(
                    TechnicalSignal(
                        name="MACD",
                        status="bullish",
                        detail="DIF above DEA; positive momentum intact" if en else "DIF 位于 DEA 上方，多头动能延续",
                    )
                )
            else:
                score -= 8
                signals.append(
                    TechnicalSignal(
                        name="MACD",
                        status="bearish",
                        detail="DIF below DEA; bearish momentum dominates" if en else "DIF 位于 DEA 下方，空头占优",
                    )
                )

        # 3. RSI
        if v_rsi is not None:
            if v_rsi >= 75:
                score -= 8
                signals.append(
                    TechnicalSignal(
                        name="RSI(14)",
                        status="bearish",
                        detail=f"RSI={v_rsi:.1f} overbought; pullback risk" if en else f"RSI={v_rsi:.1f} 进入超买区，注意回调风险",
                    )
                )
            elif v_rsi <= 25:
                score += 8
                signals.append(
                    TechnicalSignal(
                        name="RSI(14)",
                        status="bullish",
                        detail=f"RSI={v_rsi:.1f} oversold; bounce potential" if en else f"RSI={v_rsi:.1f} 进入超卖区，存在反弹修复需求",
                    )
                )
            elif v_rsi >= 55:
                score += 5
                signals.append(
                    TechnicalSignal(
                        name="RSI(14)",
                        status="bullish",
                        detail=f"RSI={v_rsi:.1f} in constructive zone" if en else f"RSI={v_rsi:.1f} 处于偏强区间",
                    )
                )
            elif v_rsi <= 45:
                score -= 5
                signals.append(
                    TechnicalSignal(
                        name="RSI(14)",
                        status="bearish",
                        detail=f"RSI={v_rsi:.1f} in weak zone" if en else f"RSI={v_rsi:.1f} 处于偏弱区间",
                    )
                )
            else:
                signals.append(
                    TechnicalSignal(
                        name="RSI(14)",
                        status="neutral",
                        detail=f"RSI={v_rsi:.1f} neutral" if en else f"RSI={v_rsi:.1f} 处于中性平衡区",
                    )
                )

        # 4. Bollinger Bands
        if v_upper is not None and v_lower is not None and v_mid is not None:
            bb_label = "Bollinger Bands" if en else "布林带"
            if latest_close >= v_upper:
                score += 4
                signals.append(
                    TechnicalSignal(
                        name=bb_label,
                        status="neutral",
                        detail="At/above upper band; strong but extended" if en else "触及/突破上轨，短线强势但需防偏离回归",
                    )
                )
            elif latest_close <= v_lower:
                score -= 4
                signals.append(
                    TechnicalSignal(
                        name=bb_label,
                        status="neutral",
                        detail="At/below lower band; near lower support" if en else "触及/跌破下轨，短线弱势但接近下沿支撑",
                    )
                )
            elif latest_close >= v_mid:
                score += 4
                signals.append(
                    TechnicalSignal(
                        name=bb_label,
                        status="bullish",
                        detail="Trading in upper channel (mid to upper)" if en else "运行于中轨与上轨之间（偏强通道）",
                    )
                )
            else:
                score -= 4
                signals.append(
                    TechnicalSignal(
                        name=bb_label,
                        status="bearish",
                        detail="Trading in lower channel (lower to mid)" if en else "运行于中轨与下轨之间（偏弱通道）",
                    )
                )

        # 5. KDJ
        if v_k is not None and v_d is not None and v_j is not None:
            if v_j > 95:
                score -= 5
                signals.append(
                    TechnicalSignal(
                        name="KDJ",
                        status="bearish",
                        detail=f"J={v_j:.1f} short-term overbought" if en else f"J={v_j:.1f} 短期严重超买",
                    )
                )
            elif v_j < 10:
                score += 5
                signals.append(
                    TechnicalSignal(
                        name="KDJ",
                        status="bullish",
                        detail=f"J={v_j:.1f} short-term oversold" if en else f"J={v_j:.1f} 短期超卖钝化",
                    )
                )
            elif v_k > v_d:
                score += 4
                signals.append(
                    TechnicalSignal(
                        name="KDJ",
                        status="bullish",
                        detail=f"K({v_k:.1f}) > D({v_d:.1f}) bullish" if en else f"K({v_k:.1f}) > D({v_d:.1f}) 偏多",
                    )
                )
            else:
                score -= 4
                signals.append(
                    TechnicalSignal(
                        name="KDJ",
                        status="bearish",
                        detail=f"K({v_k:.1f}) < D({v_d:.1f}) bearish" if en else f"K({v_k:.1f}) < D({v_d:.1f}) 偏空",
                    )
                )

        score = max(0, min(100, score))
        if score >= 75:
            rating = "Strong Bullish" if en else "强势多头"
        elif score >= 60:
            rating = "Moderately Bullish" if en else "偏多震荡"
        elif score >= 45:
            rating = "Neutral" if en else "中性震荡"
        elif score >= 30:
            rating = "Moderately Bearish" if en else "偏空震荡"
        else:
            rating = "Strong Bearish" if en else "弱势空头"

        return TechnicalReport(
            code=code,
            name=name,
            trade_date=trade_date,
            latest_close=round(latest_close, 2),
            ma5=v_ma5,
            ma10=v_ma10,
            ma20=v_ma20,
            ma60=v_ma60,
            rsi14=v_rsi,
            macd_dif=v_dif,
            macd_dea=v_dea,
            macd_hist=v_hist,
            boll_upper=v_upper,
            boll_mid=v_mid,
            boll_lower=v_lower,
            kdj_k=v_k,
            kdj_d=v_d,
            kdj_j=v_j,
            atr14=v_atr,
            volatility_20d=v_vol,
            support_level=round(support, 2),
            resistance_level=round(resistance, 2),
            score=score,
            rating=rating,
            signals=signals,
        )
