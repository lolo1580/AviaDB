<script setup>
import { computed } from 'vue'
import { TYPE_LABEL, TYPE_BADGE, STATUS_LABEL, STATUS_BADGE, formatMoney } from '../labels'
import { coverPhoto, photoUrl } from '../api'

const props = defineProps({ item: { type: Object, required: true } })
defineEmits(['edit'])

const cover = computed(() => coverPhoto(props.item))

const specifics = computed(() => {
  const it = props.item
  if (it.item_type === 'DIECAST' && it.diecast) {
    return [it.diecast.scale, it.diecast.manufacturer].filter(Boolean)
  }
  if (it.item_type === 'PATCH' && it.patch) {
    return [it.patch.unit_squadron, it.patch.base].filter(Boolean)
  }
  return []
})
</script>

<template>
  <article class="group flex flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm transition hover:shadow-md dark:border-slate-800 dark:bg-slate-900">
    <button
      type="button"
      class="relative block aspect-[4/3] w-full overflow-hidden bg-slate-100 dark:bg-slate-800"
      @click="$emit('edit', item)"
    >
      <img
        v-if="cover"
        :src="photoUrl(cover.thumb_path || cover.file_path)"
        :alt="item.name"
        loading="lazy"
        class="h-full w-full object-cover transition duration-300 group-hover:scale-105"
      />
      <div v-else class="flex h-full w-full items-center justify-center text-slate-300 dark:text-slate-600">
        <svg xmlns="http://www.w3.org/2000/svg" class="h-10 w-10" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
          <path stroke-linecap="round" stroke-linejoin="round" d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909M3.75 21h16.5A1.5 1.5 0 0021.75 19.5V4.5A1.5 1.5 0 0020.25 3H3.75A1.5 1.5 0 002.25 4.5v15A1.5 1.5 0 003.75 21z" />
        </svg>
      </div>
      <span
        class="absolute left-2 top-2 rounded-md px-2 py-0.5 text-xs font-semibold ring-1 ring-inset"
        :class="TYPE_BADGE[item.item_type]"
      >
        {{ TYPE_LABEL[item.item_type] }}
      </span>
    </button>

    <div class="flex flex-1 flex-col gap-2 p-3">
      <h3 class="line-clamp-2 text-sm font-semibold text-slate-900 dark:text-slate-100" :title="item.name">
        {{ item.name }}
      </h3>

      <div class="flex flex-wrap gap-1 text-xs">
        <span v-if="item.country" class="rounded bg-slate-100 px-1.5 py-0.5 text-slate-600 dark:bg-slate-800 dark:text-slate-300">
          {{ item.country }}
        </span>
        <span
          v-for="tag in specifics"
          :key="tag"
          class="rounded bg-slate-100 px-1.5 py-0.5 text-slate-600 dark:bg-slate-800 dark:text-slate-300"
        >
          {{ tag }}
        </span>
      </div>

      <div class="mt-auto flex items-center justify-between pt-1 text-xs">
        <span
          class="rounded px-1.5 py-0.5 font-medium ring-1 ring-inset"
          :class="STATUS_BADGE[item.status]"
        >
          {{ STATUS_LABEL[item.status] }}
        </span>
        <span v-if="item.estimated_value != null" class="font-semibold text-slate-700 dark:text-slate-200">
          {{ formatMoney(item.estimated_value, item.currency) }}
        </span>
      </div>
    </div>
  </article>
</template>
