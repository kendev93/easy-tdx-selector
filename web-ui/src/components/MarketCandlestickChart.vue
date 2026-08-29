<script setup lang="ts">
import { computed } from 'vue'

import type { MarketCandle, MarketChartPeriod } from '../types'

interface Props {
  candles: MarketCandle[]
  maKeys: string[]
  period: MarketChartPeriod
  showMacd: boolean
  showRsi: boolean
}

interface Bounds {
  min: number
  max: number
}

const props = defineProps<Props>()

const WIDTH = 960
const LEFT = 48
const RIGHT = 16
const PLOT_WIDTH = WIDTH - LEFT - RIGHT
const PRICE_TOP = 18
const PRICE_HEIGHT = 300
const VOLUME_HEIGHT = 72
const INDICATOR_HEIGHT = 100
const MAX_CANDLES = 220
const MA_COLORS = ['#86efac', '#67e8f9', '#c4b5fd', '#fbbf24', '#fb7185', '#f9a8d4']

const displayedCandles = computed(() => (
  props.candles.length > MAX_CANDLES ? props.candles.slice(-MAX_CANDLES) : props.candles
))

const layout = computed(() => {
  const volumeTop = PRICE_TOP + PRICE_HEIGHT + 34
  let cursor = volumeTop + VOLUME_HEIGHT + 30
  const rsiTop = props.showRsi ? cursor : null
  if (props.showRsi) cursor += INDICATOR_HEIGHT + 28
  const macdTop = props.showMacd ? cursor : null
  if (props.showMacd) cursor += INDICATOR_HEIGHT + 28
  return { volumeTop, rsiTop, macdTop, height: cursor }
})

const priceBounds = computed<Bounds>(() => {
  const values = displayedCandles.value.flatMap((candle) => [candle.high, candle.low])
    .filter((value): value is number => value !== null && Number.isFinite(value))
  if (!values.length) return { min: 0, max: 1 }
  const minimum = Math.min(...values)
  const maximum = Math.max(...values)
  const padding = (maximum - minimum) * 0.06 || Math.max(Math.abs(maximum) * 0.02, 1)
  return { min: minimum - padding, max: maximum + padding }
})

const macdBounds = computed<Bounds>(() => {
  const values = displayedCandles.value.flatMap((candle) => [
    candle.macd,
    candle.macd_signal,
    candle.macd_histogram,
  ]).filter((value): value is number => value !== null && Number.isFinite(value))
  if (!values.length) return { min: -1, max: 1 }
  const maximum = Math.max(...values)
  const minimum = Math.min(...values)
  const padding = (maximum - minimum) * 0.12 || 1
  return { min: minimum - padding, max: maximum + padding }
})

const volumeMax = computed(() => {
  const values = displayedCandles.value.map((candle) => candle.volume ?? 0).filter(Number.isFinite)
  return Math.max(...values, 1)
})

const step = computed(() => PLOT_WIDTH / Math.max(displayedCandles.value.length, 1))
const candleWidth = computed(() => Math.max(2, Math.min(13, step.value * 0.68)))

const priceTicks = computed(() => {
  const { min, max } = priceBounds.value
  return [max, (max + min) / 2, min].map((value) => ({ value, y: priceY(value) }))
})

const xLabels = computed(() => {
  const count = displayedCandles.value.length
  const indexes = [...new Set([0, Math.floor((count - 1) / 2), Math.max(count - 1, 0)])]
  return indexes.map((index) => ({ index, x: xFor(index), label: displayedCandles.value[index]?.date ?? '' }))
})

const maSeries = computed(() => props.maKeys.map((key, index) => ({
  key,
  label: key.toUpperCase(),
  color: MA_COLORS[index % MA_COLORS.length],
  points: linePoints((candle) => candle.ma[key], PRICE_TOP, PRICE_HEIGHT, priceBounds.value),
})))

const rsiPoints = computed(() => linePoints(
  (candle) => candle.rsi14,
  layout.value.rsiTop ?? 0,
  INDICATOR_HEIGHT,
  { min: 0, max: 100 },
))

const macdSeries = computed(() => [
  {
    key: 'macd',
    label: 'MACD',
    color: '#67e8f9',
    points: linePoints((candle) => candle.macd, layout.value.macdTop ?? 0, INDICATOR_HEIGHT, macdBounds.value),
  },
  {
    key: 'macd_signal',
    label: 'SIGNAL',
    color: '#fbbf24',
    points: linePoints((candle) => candle.macd_signal, layout.value.macdTop ?? 0, INDICATOR_HEIGHT, macdBounds.value),
  },
])

const macdBars = computed(() => displayedCandles.value.flatMap((candle, index) => {
  const value = candle.macd_histogram
  if (value === null || !Number.isFinite(value)) return []
  const zero = indicatorY(0, layout.value.macdTop ?? 0, INDICATOR_HEIGHT, macdBounds.value)
  const y = indicatorY(value, layout.value.macdTop ?? 0, INDICATOR_HEIGHT, macdBounds.value)
  return [{
      x: xFor(index) - candleWidth.value * 0.35,
      y: Math.min(y, zero),
      height: Math.max(Math.abs(y - zero), 1),
      positive: value >= 0,
    }]
}))

function numeric(value: number | null, fallback = 0): number {
  return value !== null && Number.isFinite(value) ? value : fallback
}

function xFor(index: number): number {
  return LEFT + (index + 0.5) * step.value
}

function priceY(value: number): number {
  return scale(value, PRICE_TOP, PRICE_HEIGHT, priceBounds.value)
}

function indicatorY(value: number, top: number, height: number, bounds: Bounds): number {
  return scale(value, top, height, bounds)
}

function scale(value: number, top: number, height: number, bounds: Bounds): number {
  const span = bounds.max - bounds.min || 1
  return top + height - ((value - bounds.min) / span) * height
}

function linePoints(
  getter: (candle: MarketCandle) => number | null,
  top: number,
  height: number,
  bounds: Bounds,
): string {
  return displayedCandles.value.map((candle, index) => {
    const value = getter(candle)
    return value === null || !Number.isFinite(value) ? null : `${xFor(index).toFixed(1)},${indicatorY(value, top, height, bounds).toFixed(1)}`
  }).filter((point): point is string => point !== null).join(' ')
}

function volumeHeight(value: number | null): number {
  return (numeric(value) / volumeMax.value) * VOLUME_HEIGHT
}

function volumeY(value: number | null): number {
  return layout.value.volumeTop + VOLUME_HEIGHT - volumeHeight(value)
}

function isUp(candle: MarketCandle): boolean {
  return numeric(candle.close) >= numeric(candle.open)
}

function bodyY(candle: MarketCandle): number {
  return priceY(Math.max(numeric(candle.open), numeric(candle.close)))
}

function bodyHeight(candle: MarketCandle): number {
  return Math.max(Math.abs(priceY(numeric(candle.open)) - priceY(numeric(candle.close))), 1)
}

function formatAxis(value: number): string {
  return value >= 100 ? value.toFixed(0) : value.toFixed(2)
}
</script>

<template>
  <div v-if="!displayedCandles.length" class="market-chart-empty" data-testid="market-chart-empty">
    暂无可展示的行情数据
  </div>
  <div v-else class="market-chart" data-testid="market-candlestick-chart">
    <div class="market-chart-legend">
      <span class="legend-candle-up">涨</span><span class="legend-candle-down">跌</span>
      <span v-for="series in maSeries" :key="series.key" class="legend-line"><i :style="{ background: series.color }"></i>{{ series.label }}</span>
      <span v-if="showRsi" class="legend-line"><i class="legend-rsi"></i>RSI14</span>
      <span v-if="showMacd" class="legend-line"><i class="legend-macd"></i>MACD</span>
    </div>
    <svg class="market-chart-svg" :viewBox="`0 0 ${WIDTH} ${layout.height}`" role="img" aria-label="本地行情 K 线图">
      <g class="chart-grid">
        <line v-for="tick in priceTicks" :key="tick.y" :x1="LEFT" :x2="WIDTH - RIGHT" :y1="tick.y" :y2="tick.y"></line>
        <text v-for="tick in priceTicks" :key="`label-${tick.y}`" :x="LEFT - 8" :y="tick.y + 3" text-anchor="end">{{ formatAxis(tick.value) }}</text>
      </g>
      <g class="candles">
        <g v-for="(candle, index) in displayedCandles" :key="candle.date">
          <line :x1="xFor(index)" :x2="xFor(index)" :y1="priceY(numeric(candle.high))" :y2="priceY(numeric(candle.low))" :class="isUp(candle) ? 'candle-wick-up' : 'candle-wick-down'"></line>
          <rect :x="xFor(index) - candleWidth / 2" :y="bodyY(candle)" :width="candleWidth" :height="bodyHeight(candle)" :class="isUp(candle) ? 'candle-body-up' : 'candle-body-down'">
            <title>{{ candle.date }} 开 {{ numeric(candle.open).toFixed(2) }} 高 {{ numeric(candle.high).toFixed(2) }} 低 {{ numeric(candle.low).toFixed(2) }} 收 {{ numeric(candle.close).toFixed(2) }}</title>
          </rect>
        </g>
      </g>
      <g class="ma-lines">
        <polyline v-for="series in maSeries" :key="series.key" :points="series.points" :stroke="series.color"></polyline>
      </g>
      <g class="volume-panel">
        <line :x1="LEFT" :x2="WIDTH - RIGHT" :y1="layout.volumeTop + VOLUME_HEIGHT" :y2="layout.volumeTop + VOLUME_HEIGHT"></line>
        <rect v-for="(candle, index) in displayedCandles" :key="`volume-${candle.date}`" :x="xFor(index) - candleWidth / 2" :y="volumeY(candle.volume)" :width="candleWidth" :height="volumeHeight(candle.volume)" :class="isUp(candle) ? 'volume-up' : 'volume-down'"></rect>
        <text :x="LEFT" :y="layout.volumeTop + 13">VOL</text>
      </g>
      <g v-if="showRsi && layout.rsiTop !== null" class="indicator-panel">
        <line :x1="LEFT" :x2="WIDTH - RIGHT" :y1="indicatorY(70, layout.rsiTop, INDICATOR_HEIGHT, { min: 0, max: 100 })" :y2="indicatorY(70, layout.rsiTop, INDICATOR_HEIGHT, { min: 0, max: 100 })" class="indicator-guide"></line>
        <line :x1="LEFT" :x2="WIDTH - RIGHT" :y1="indicatorY(30, layout.rsiTop, INDICATOR_HEIGHT, { min: 0, max: 100 })" :y2="indicatorY(30, layout.rsiTop, INDICATOR_HEIGHT, { min: 0, max: 100 })" class="indicator-guide"></line>
        <polyline :points="rsiPoints" class="rsi-line"></polyline>
        <text :x="LEFT" :y="layout.rsiTop + 13">RSI14</text><text :x="WIDTH - RIGHT" :y="indicatorY(70, layout.rsiTop, INDICATOR_HEIGHT, { min: 0, max: 100 }) + 3" text-anchor="end">70</text><text :x="WIDTH - RIGHT" :y="indicatorY(30, layout.rsiTop, INDICATOR_HEIGHT, { min: 0, max: 100 }) + 3" text-anchor="end">30</text>
      </g>
      <g v-if="showMacd && layout.macdTop !== null" class="indicator-panel">
        <line :x1="LEFT" :x2="WIDTH - RIGHT" :y1="indicatorY(0, layout.macdTop, INDICATOR_HEIGHT, macdBounds)" :y2="indicatorY(0, layout.macdTop, INDICATOR_HEIGHT, macdBounds)" class="indicator-guide"></line>
        <rect v-for="(bar, index) in macdBars" :key="`macd-bar-${index}`" :x="bar.x" :y="bar.y" :width="candleWidth * 0.7" :height="bar.height" :class="bar.positive ? 'macd-bar-positive' : 'macd-bar-negative'"></rect>
        <polyline v-for="series in macdSeries" :key="series.key" :points="series.points" :stroke="series.color"></polyline>
        <text :x="LEFT" :y="layout.macdTop + 13">MACD</text>
      </g>
      <g class="chart-x-axis">
        <text v-for="label in xLabels" :key="label.index" :x="label.x" :y="layout.height - 5" text-anchor="middle">{{ label.label }}</text>
      </g>
    </svg>
    <p class="market-chart-note">{{ props.candles.length > MAX_CANDLES ? `图表显示最近 ${MAX_CANDLES} 根，完整本地数据共 ${props.candles.length} 根。` : `共 ${props.candles.length} 根 ${period === 'daily' ? '日' : period === 'monthly' ? '月' : '年'}线。` }}</p>
  </div>
</template>
