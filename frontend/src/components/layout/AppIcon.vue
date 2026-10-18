<script setup>
import { iconPaths } from '../../layout/icons'

defineProps({
  name: { type: String, required: true },
  size: { type: String, default: 'h-5 w-5' },
  strokeWidth: { type: [String, Number], default: 1.7 },
})
</script>

<template>
  <svg
    :class="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    :stroke-width="strokeWidth"
    aria-hidden="true"
  >
    <path
      v-for="(path, index) in iconPaths(name)"
      :key="index"
      stroke-linecap="round"
      stroke-linejoin="round"
      :d="path"
    />
  </svg>
</template>
