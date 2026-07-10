import { useEffect, useMemo, useState } from 'react'
import { Search, ShoppingCart, TrendingDown } from 'lucide-react'

import {
  compareProduct,
  getCbaSummary,
  getDataMode,
  getEconomicScenario,
  getHealth,
  getMetadata,
  getPremiumScenario,
  getProductSummary,
  searchProducts,
} from './api'
import DataTable from './components/DataTable'
import MetricCard from './components/MetricCard'
import SectionCard from './components/SectionCard'

function formatCurrency(value) {
  const parsed = Number(value)
  if (Number.isNaN(parsed)) return value ?? '—'
  return parsed.toLocaleString('es-CL', {
    style: 'currency',
    currency: 'CLP',
    maximumFractionDigits: 0,
  })
}

function Pill({ children }) {
  return <span className="rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">{children}</span>
}

function Muted({ children }) {
  return <span className="text-slate-400">{children}</span>
}

function formatBrand(value) {
  return value ? String(value) : <Muted>No informada</Muted>
}

function formatItemsCoverage(found, total, formattedPct) {
  if (found === null || found === undefined || total === null || total === undefined) return '—'
  return `${Number(found).toLocaleString('es-CL')} de ${Number(total).toLocaleString('es-CL')} (${formattedPct ?? '—'})`
}

function ItemList({ items = [], limit = 8 }) {
  if (!items.length) return <Muted>Sin detalle disponible</Muted>

  const visible = items.slice(0, limit)
  const remaining = items.length - visible.length

  return (
    <div className="flex max-w-[520px] flex-wrap gap-1.5">
      {visible.map((item) => (
        <span key={item} className="rounded-md bg-slate-100 px-2 py-1 text-xs text-slate-700">
          {item}
        </span>
      ))}
      {remaining > 0 ? (
        <span className="rounded-md bg-slate-200 px-2 py-1 text-xs font-semibold text-slate-700">
          +{remaining}
        </span>
      ) : null}
    </div>
  )
}

export default function App() {
  const [health, setHealth] = useState(null)
  const [metadata, setMetadata] = useState(null)
  const [summary, setSummary] = useState(null)
  const [cba, setCba] = useState(null)
  const [economic, setEconomic] = useState(null)
  const [premium, setPremium] = useState(null)
  const [query, setQuery] = useState('leche')
  const [market, setMarket] = useState('')
  const [searchResult, setSearchResult] = useState([])
  const [comparison, setComparison] = useState(null)
  const [loading, setLoading] = useState(true)
  const [searching, setSearching] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    async function loadInitialData() {
      try {
        setLoading(true)
        const [healthData, metadataData, summaryData, cbaData, economicData, premiumData] = await Promise.all([
          getHealth(),
          getMetadata(),
          getProductSummary(),
          getCbaSummary(),
          getEconomicScenario(),
          getPremiumScenario(),
        ])

        setHealth(healthData)
        setMetadata(metadataData)
        setSummary(summaryData)
        setCba(cbaData)
        setEconomic(economicData)
        setPremium(premiumData)
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }

    loadInitialData()
  }, [])

  useEffect(() => {
    handleSearch()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function handleSearch(event) {
    event?.preventDefault()
    if (!query.trim()) return

    try {
      setSearching(true)
      const [results, compare] = await Promise.all([
        searchProducts(query, market, 30),
        compareProduct(query),
      ])
      setSearchResult(results.items ?? [])
      setComparison(compare)
    } catch (err) {
      setError(err.message)
    } finally {
      setSearching(false)
    }
  }

  const latestConsolidado = metadata?.files?.consolidado
  const bestCbaMarket = cba?.resumen_supermercado?.[0]
  const bestEconomic = economic?.total_por_supermercado?.[0]
  const bestPremium = premium?.total_por_supermercado?.[0]
  const dataModeLabel = getDataMode() === 'static' ? 'Datos estáticos' : 'API'
  const dataSourceLabel = getDataMode() === 'static' ? 'Datos leídos desde JSON estático' : 'Datos leídos desde FastAPI'
  const cbaItemsByMarket = useMemo(() => {
    const entries = cba?.items_by_supermarket ?? []
    return Object.fromEntries(entries.map((item) => [item.supermarket, item.covered_items ?? []]))
  }, [cba])

  function scenarioItemsForMarket(dataset, supermarket) {
    const priceKey = `price_${supermarket}`
    return (dataset?.resumen_final ?? [])
      .filter((item) => item[priceKey] !== null && item[priceKey] !== undefined && item[priceKey] !== '')
      .map((item) => item.cba_name)
  }

  const productColumns = useMemo(
    () => [
      { key: 'name', label: 'Producto' },
      { key: 'brand', label: 'Marca', render: formatBrand },
      { key: 'supermarket', label: 'Supermercado', render: (value) => <Pill>{value}</Pill> },
      { key: 'price', label: 'Precio', render: formatCurrency },
      { key: 'discount_price', label: 'Oferta', render: formatCurrency },
      { key: 'category_std', label: 'Categoría' },
    ],
    [],
  )

  const cbaColumns = [
    { key: 'supermarket', label: 'Supermercado', render: (value) => <Pill>{value}</Pill> },
    { key: 'costo_total_cba_detectada', label: 'Costo detectado', render: formatCurrency },
    {
      key: 'cba_items_cubiertos',
      label: 'Cobertura CBA',
      render: (_value, row) => formatItemsCoverage(row.cba_items_cubiertos, row.cba_items_totales, row.cobertura_pct_fmt),
    },
    {
      key: 'covered_items',
      label: 'Ítems cubiertos',
      render: (_value, row) => <ItemList items={cbaItemsByMarket[row.supermarket] ?? []} />,
    },
  ]

  const economicColumns = [
    { key: 'supermarket', label: 'Supermercado', render: (value) => <Pill>{value}</Pill> },
    { key: 'ranking_economico', label: 'Ranking' },
    { key: 'total_cba_economica', label: 'Total estimado', render: formatCurrency },
    {
      key: 'productos_encontrados',
      label: 'Cobertura',
      render: (_value, row) => formatItemsCoverage(row.productos_encontrados, row.productos_cba_objetivo, row.cobertura_pct_fmt),
    },
    {
      key: 'items_considerados',
      label: 'Ítems considerados',
      render: (_value, row) => <ItemList items={scenarioItemsForMarket(economic, row.supermarket)} limit={6} />,
    },
  ]

  const premiumColumns = [
    { key: 'supermarket', label: 'Supermercado', render: (value) => <Pill>{value}</Pill> },
    { key: 'ranking_premium', label: 'Ranking' },
    { key: 'total_cba_premium', label: 'Total estimado', render: formatCurrency },
    {
      key: 'productos_encontrados',
      label: 'Cobertura',
      render: (_value, row) => formatItemsCoverage(row.productos_encontrados, row.productos_cba_objetivo, row.cobertura_pct_fmt),
    },
    {
      key: 'items_considerados',
      label: 'Ítems considerados',
      render: (_value, row) => <ItemList items={scenarioItemsForMarket(premium, row.supermarket)} limit={6} />,
    },
  ]

  const scenarioDetailColumns = [
    { key: 'cba_name', label: 'Ítem CBA' },
    { key: 'best_name', label: 'Producto elegido' },
    { key: 'best_brand', label: 'Marca', render: formatBrand },
    { key: 'best_supermarket', label: 'Mejor supermercado', render: (value) => <Pill>{value}</Pill> },
    { key: 'best_price_num', label: 'Precio', render: formatCurrency },
  ]

  return (
    <main className="min-h-screen bg-soft text-ink">
      <section className="bg-gradient-to-br from-emerald-700 via-emerald-600 to-lime-500 px-4 py-10 text-white sm:px-6 lg:px-8">
        <div className="mx-auto max-w-7xl">
          <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
            <div className="max-w-3xl">
              <h1 className="text-4xl font-black tracking-tight sm:text-5xl">
                Comparador de precios de supermercados
              </h1>
              <p className="mt-4 text-lg text-emerald-50">
                Explora productos consolidados, costos de CBA y escenarios económico/premium usando las salidas reales del pipeline.
              </p>
            </div>
            <div className="rounded-3xl bg-white/15 p-5 backdrop-blur">
              <p className="text-sm text-emerald-50">Fuente de datos</p>
              <p className="mt-1 text-2xl font-bold">{health?.status === 'ok' ? dataModeLabel : 'Pendiente'}</p>
              <p className="mt-2 text-sm text-emerald-50">
                Consolidado: {health?.consolidado_rows?.toLocaleString('es-CL') ?? '—'} filas
              </p>
            </div>
          </div>
        </div>
      </section>

      <div className="mx-auto max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
        {error ? (
          <div className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            {error}
          </div>
        ) : null}

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <MetricCard
            label="Productos consolidados"
            value={summary?.total_products?.toLocaleString('es-CL') ?? (loading ? '...' : '0')}
            helper={latestConsolidado?.file_name ?? 'Ejecuta extraccion_limpieza.py para actualizar'}
          />
          <MetricCard
            label="Supermercado CBA más barato"
            value={bestCbaMarket?.supermarket ?? '—'}
            helper={bestCbaMarket ? formatCurrency(bestCbaMarket.costo_total_cba_detectada) : 'Sin resumen CBA'}
          />
          <MetricCard
            label="Escenario económico"
            value={bestEconomic?.supermarket ?? '—'}
            helper={bestEconomic ? formatCurrency(bestEconomic.total_cba_economica) : 'Sin datos'}
          />
          <MetricCard
            label="Escenario premium"
            value={bestPremium?.supermarket ?? '—'}
            helper={bestPremium ? formatCurrency(bestPremium.total_cba_premium) : 'Sin datos'}
          />
        </section>

        <SectionCard
          title="Buscador de productos"
          description="Busca productos, precios y supermercado. En Lider la marca no viene informada desde el archivo de origen."
          action={
            <div className="flex items-center gap-2 text-sm text-muted">
              <ShoppingCart className="h-4 w-4" />
              {dataSourceLabel}
            </div>
          }
        >
          <form onSubmit={handleSearch} className="mb-5 grid gap-3 md:grid-cols-[1fr_180px_auto]">
            <label className="relative">
              <Search className="pointer-events-none absolute left-3 top-3 h-5 w-5 text-slate-400" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                className="w-full rounded-2xl border border-slate-300 bg-white py-3 pl-10 pr-4 outline-none transition focus:border-emerald-500 focus:ring-4 focus:ring-emerald-100"
                placeholder="Buscar producto: leche, arroz, aceite..."
              />
            </label>
            <select
              value={market}
              onChange={(event) => setMarket(event.target.value)}
              className="rounded-2xl border border-slate-300 bg-white px-4 py-3 outline-none transition focus:border-emerald-500 focus:ring-4 focus:ring-emerald-100"
            >
              <option value="">Todos</option>
              {metadata?.supermarkets?.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
            <button
              type="submit"
              className="rounded-2xl bg-brand px-6 py-3 font-bold text-white transition hover:bg-brandDark disabled:cursor-not-allowed disabled:opacity-60"
              disabled={searching}
            >
              {searching ? 'Buscando...' : 'Buscar'}
            </button>
          </form>

          <DataTable columns={productColumns} rows={searchResult} emptyMessage="Busca un producto para ver resultados." />

          {comparison?.markets?.length ? (
            <div className="mt-6 grid gap-4 lg:grid-cols-3">
              {comparison.markets.map((group) => (
                <div key={group.supermarket} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                  <h3 className="font-bold capitalize text-ink">{group.supermarket}</h3>
                  <ul className="mt-3 space-y-2 text-sm text-slate-700">
                    {group.items.slice(0, 3).map((item, index) => (
                      <li key={`${item.sku}-${index}`} className="rounded-xl bg-white p-3">
                        <p className="font-medium">{item.name}</p>
                        <p className="mt-1 text-muted">{formatCurrency(item.price)}</p>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          ) : null}
        </SectionCard>

        <SectionCard
          title="Resumen CBA por supermercado"
          description="Costo estimado para los productos de la Canasta Básica de Alimentos que el pipeline logró encontrar. La columna de ítems muestra ejemplos concretos cubiertos por cada supermercado."
        >
          <DataTable columns={cbaColumns} rows={cba?.resumen_supermercado ?? []} />
        </SectionCard>

        <div className="grid gap-8 xl:grid-cols-2">
          <SectionCard
            title="Escenario económico"
            description="Selecciona el menor precio detectado por ítem CBA. La cobertura indica cuántos ítems de la canasta entraron al cálculo."
            action={<TrendingDown className="h-5 w-5 text-emerald-600" />}
          >
            <DataTable columns={economicColumns} rows={economic?.total_por_supermercado ?? []} />
          </SectionCard>

          <SectionCard
            title="Escenario premium"
            description="Prioriza productos con mejor calce y atributos de marca/formato. La cobertura baja significa que el criterio fue más estricto."
          >
            <DataTable columns={premiumColumns} rows={premium?.total_por_supermercado ?? []} />
          </SectionCard>
        </div>

        <div className="grid gap-8 xl:grid-cols-2">
          <SectionCard
            title="Productos elegidos en escenario económico"
            description="Producto concreto usado como referencia para cada ítem CBA encontrado."
          >
            <DataTable columns={scenarioDetailColumns} rows={economic?.resumen_final ?? []} />
          </SectionCard>

          <SectionCard
            title="Productos elegidos en escenario premium"
            description="Selección premium disponible; por ahora cubre menos ítems que el escenario económico."
          >
            <DataTable columns={scenarioDetailColumns} rows={premium?.resumen_final ?? []} />
          </SectionCard>
        </div>
      </div>
    </main>
  )
}
