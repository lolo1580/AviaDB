// Libellés métier et styles de badges partagés par les composants.

export const TYPE_LABEL = {
  DIECAST: 'Maquette',
  PATCH: 'Patch',
  OTHER: 'Autre',
}

export const TYPE_BADGE = {
  DIECAST: 'bg-sky-100 text-sky-800 ring-sky-600/20 dark:bg-sky-950 dark:text-sky-300 dark:ring-sky-400/30',
  PATCH: 'bg-violet-100 text-violet-800 ring-violet-600/20 dark:bg-violet-950 dark:text-violet-300 dark:ring-violet-400/30',
  OTHER: 'bg-slate-100 text-slate-700 ring-slate-500/20 dark:bg-slate-800 dark:text-slate-300 dark:ring-slate-400/30',
}

export const STATUS_LABEL = {
  EXHIBITED: 'Exposé',
  STORED_BOX: 'En boîte',
  WANTED: 'Recherché',
  TRANSIT: 'En transit',
}

export const STATUS_BADGE = {
  EXHIBITED: 'bg-emerald-100 text-emerald-800 ring-emerald-600/20 dark:bg-emerald-950 dark:text-emerald-300 dark:ring-emerald-400/30',
  STORED_BOX: 'bg-amber-100 text-amber-800 ring-amber-600/20 dark:bg-amber-950 dark:text-amber-300 dark:ring-amber-400/30',
  WANTED: 'bg-rose-100 text-rose-800 ring-rose-600/20 dark:bg-rose-950 dark:text-rose-300 dark:ring-rose-400/30',
  TRANSIT: 'bg-slate-100 text-slate-700 ring-slate-500/20 dark:bg-slate-800 dark:text-slate-300 dark:ring-slate-400/30',
}

export const MATERIAL_LABEL = {
  EMBROIDERED: 'Broderie',
  PVC: 'PVC',
  LEATHER: 'Cuir',
  WOVEN: 'Tissé',
}

export const ATTACHMENT_LABEL = {
  HOOK_VELCRO: 'Velcro crochet',
  LOOP_VELCRO: 'Velcro boucle',
  SEW_ON: 'À coudre',
}

export const SHAPE_LABEL = {
  ROUND: 'Rond',
  SHIELD: 'Écusson',
  TAB: 'Fanion',
  CUT_OUT: 'Découpé',
}

export function formatMoney(value, currency = 'EUR') {
  if (value === null || value === undefined || value === '') return null
  try {
    return new Intl.NumberFormat('fr-FR', { style: 'currency', currency }).format(value)
  } catch {
    return `${new Intl.NumberFormat('fr-FR', { minimumFractionDigits: 2 }).format(value)} ${currency}`
  }
}
