export interface SettingsPreset {
  id: string
  name: string
  description: string
  values: Record<string, unknown>
}

export const PRESETS: SettingsPreset[] = [
  {
    id: 'default',
    name: 'Alapértelmezett',
    description:
      'Kiegyensúlyozott elemzés, a rendszer alapértelmezett értékeivel. Megbízható eredmények a legtöbb úttípuson.',
    values: {
      edge_density_weight: 15.0,
      rqi_threshold_excellent: 15.0,
      rqi_threshold_good: 25.0,
      magic_wand_conf: 0.25,
    },
  },
  {
    id: 'precise',
    name: 'Precíziós',
    description:
      'Szigorúbb feltételek és magasabb minőségi elvárások. Csak a valóban hibátlan útszakaszok kapnak kiváló minősítést.',
    values: {
      edge_density_weight: 25.0,
      edge_density_fine_weight: 15.0,
      rqi_threshold_excellent: 10.0,
      rqi_threshold_good: 20.0,
      magic_wand_conf: 0.45,
    },
  },
  {
    id: 'quick_scan',
    name: 'Érzékeny (Gyors áttekintés)',
    description:
      'Alacsonyabb küszöbértékek az AI detektáláshoz. Több potenciális úthibát jelez előre, ideális gyors elemzéshez.',
    values: {
      edge_density_weight: 10.0,
      rqi_threshold_excellent: 20.0,
      rqi_threshold_good: 35.0,
      magic_wand_conf: 0.15,
    },
  },
]
