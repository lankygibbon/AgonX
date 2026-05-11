<script setup>
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { formatWorkoutTotal } from '../lib/ranking.js'

use([CanvasRenderer, BarChart, GridComponent, TooltipComponent])

const props = defineProps({
  ranked:          { type: Array,  default: () => [] },
  predictedResult: { type: Object, default: null },
  workoutSchema:   { type: Object, default: null },
})

const real = computed(() => props.ranked.filter(c => !c._isPredicted))
const totalCount = computed(() => real.value.length)
const position = computed(() => props.predictedResult?.overallRank)

const percentile = computed(() => {
  if (!position.value || !totalCount.value) return null
  return Math.round((1 - (position.value - 1) / totalCount.value) * 100)
})

const workoutEntries = computed(() =>
  props.workoutSchema ? Object.entries(props.workoutSchema) : []
)

function workoutTotal(competitor, wkey) {
  const entry = competitor.scores?.[wkey]
  if (!entry) return null
  if (entry.total != null) return entry.total
  const vals = Object.values(entry.components || {})
  return vals.length ? vals.reduce((a, b) => a + b, 0) : null
}

function countScored(wkey) {
  return real.value.filter(c => c.workoutRanks?.[wkey] != null).length
}

function chartOptions(wkey, wdef) {
  const scores = real.value.map(c => workoutTotal(c, wkey)).filter(v => v !== null)
  if (!scores.length) return null

  const userTotal = workoutTotal(props.predictedResult, wkey)

  const min = Math.min(...scores)
  const max = Math.max(...scores)
  const range = max - min || 1
  const binCount = Math.max(5, Math.min(12, Math.ceil(Math.sqrt(scores.length))))
  const binWidth = range / binCount

  const bins = Array.from({ length: binCount }, (_, i) => ({
    lo: min + i * binWidth,
    hi: min + (i + 1) * binWidth,
    count: 0,
    hasUser: false,
  }))

  for (const s of scores) {
    const idx = Math.min(Math.floor((s - min) / binWidth), binCount - 1)
    bins[idx].count++
  }

  if (userTotal !== null) {
    const idx = Math.min(Math.floor((userTotal - min) / binWidth), binCount - 1)
    if (idx >= 0 && idx < bins.length) bins[idx].hasUser = true
  }

  const fmt = (v) => {
    if (wdef.unit === 'time') {
      const m = Math.floor(v / 60)
      const s = Math.round(v % 60)
      return `${m}:${String(s).padStart(2, '0')}`
    }
    if (wdef.unit === 'km') return v.toFixed(2)
    return String(Math.round(v))
  }

  const unitLabel = wdef.unit === 'time' ? '' : wdef.unit

  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#1e293b',
      borderColor: '#334155',
      textStyle: { color: '#cbd5e1', fontSize: 11 },
      formatter: (params) => {
        const b = bins[params[0].dataIndex]
        return `${fmt(b.lo)}–${fmt(b.hi)}${unitLabel}<br/><b>${params[0].value}</b> athletes`
      },
    },
    grid: { top: 4, right: 4, bottom: 28, left: 30 },
    xAxis: {
      type: 'category',
      data: bins.map(b => fmt(b.lo)),
      axisLabel: { color: '#475569', fontSize: 9, rotate: wdef.unit === 'time' ? 30 : 0 },
      axisLine: { lineStyle: { color: '#1e293b' } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      axisLabel: { color: '#475569', fontSize: 9 },
      splitLine: { lineStyle: { color: '#1e293b', type: 'dashed' } },
    },
    series: [{
      type: 'bar',
      barMaxWidth: 36,
      data: bins.map(b => ({
        value: b.count,
        itemStyle: {
          color: b.hasUser ? '#f97316' : '#1e3a5f',
          borderRadius: [2, 2, 0, 0],
        },
      })),
    }],
  }
}
</script>

<template>
  <div class="mb-8 space-y-4">
    <!-- Summary cards: 2 cols on mobile, expands automatically on wider screens -->
    <div class="grid gap-3" style="grid-template-columns: repeat(auto-fit, minmax(130px, 1fr))">
      <div class="bg-slate-800 border border-slate-700 rounded-xl p-4">
        <div class="text-xs text-slate-500 uppercase tracking-wide mb-1">Overall rank</div>
        <div class="text-3xl font-bold text-white">#{{ position }}</div>
        <div class="text-sm text-slate-400 mt-0.5">of {{ totalCount }}</div>
      </div>

      <div class="bg-slate-800 border border-slate-700 rounded-xl p-4">
        <div class="text-xs text-slate-500 uppercase tracking-wide mb-1">Percentile</div>
        <div class="text-3xl font-bold text-orange-400">Top {{ percentile }}%</div>
        <div class="text-sm text-slate-400 mt-0.5">{{ totalCount - position + 1 }} above you</div>
      </div>

      <div
        v-for="[wkey, wdef] in workoutEntries"
        :key="wkey"
        class="bg-slate-800 border border-slate-700 rounded-xl p-4"
      >
        <div class="text-xs text-slate-500 uppercase tracking-wide mb-1 truncate">{{ wdef.name }}</div>
        <div class="text-2xl font-bold text-white">
          {{ predictedResult.workoutRanks?.[wkey] != null ? `#${predictedResult.workoutRanks[wkey]}` : '—' }}
        </div>
        <div class="text-xs text-slate-500 mt-0.5">
          of {{ countScored(wkey) }}
        </div>
        <div class="text-sm text-slate-300 mt-1 truncate">
          {{ formatWorkoutTotal(predictedResult, wkey, wdef) }}
        </div>
      </div>
    </div>

    <!-- Distribution charts: 1 col mobile, 2 col tablet, 3 col desktop -->
    <div
      class="grid grid-cols-1 gap-4"
      :class="{
        'max-w-sm mx-auto': workoutEntries.length === 1,
        'sm:grid-cols-2': workoutEntries.length === 2,
        'sm:grid-cols-2 lg:grid-cols-3': workoutEntries.length >= 3,
      }"
    >
      <div
        v-for="[wkey, wdef] in workoutEntries"
        :key="wkey"
        class="bg-slate-800 border border-slate-700 rounded-xl p-4"
      >
        <div class="text-xs text-slate-400 font-medium mb-3">
          {{ wdef.name }} distribution
          <span class="text-slate-600 font-normal ml-1">
            ({{ countScored(wkey) }} athletes · orange = you)
          </span>
        </div>
        <VChart
          v-if="chartOptions(wkey, wdef)"
          :option="chartOptions(wkey, wdef)"
          style="height: 130px"
          autoresize
        />
        <div v-else class="text-xs text-slate-600 italic py-6 text-center">No score data entered</div>
      </div>
    </div>
  </div>
</template>
