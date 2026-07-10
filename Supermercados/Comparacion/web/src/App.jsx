import { useEffect, useMemo, useState } from 'react'
import { Plus, Search, ShoppingCart, Trash2, TrendingDown } from 'lucide-react'

import {
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

function priceNumber(value) {
  const parsed = Number(String(value ?? '').replace(/\./g, '').replace(',', '.'))
  return Number.isNaN(parsed) ? Number.POSITIVE_INFINITY : parsed
}

function normalizeText(value) {
  return String(value ?? '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim()
}

function normalizeUnit(unit) {
  const clean = normalizeText(unit).replace(/\./g, '')
  if (['kg', 'kilo', 'kilos'].includes(clean)) return { family: 'mass', unit: 'kg', factor: 1000 }
  if (['g', 'gr', 'gramo', 'gramos'].includes(clean)) return { family: 'mass', unit: 'g', factor: 1 }
  if (['l', 'lt', 'lts', 'litro', 'litros'].includes(clean)) return { family: 'volume', unit: 'L', factor: 1000 }
  if (['ml', 'cc'].includes(clean)) return { family: 'volume', unit: clean, factor: 1 }
  return null
}

function formatSize(size) {
  if (!size) return 'Formato no detectado'
  if (size.family === 'mass') {
    return size.amount >= 1000 ? `${size.amount / 1000} kg` : `${size.amount} g`
  }
  if (size.family === 'volume') {
    return size.amount >= 1000 ? `${size.amount / 1000} L` : `${size.amount} ml`
  }
  return 'Formato no detectado'
}

function extractSizeFromText(value) {
  const text = normalizeText(value).replace(/,/g, '.')
  const matches = Array.from(text.matchAll(/(\d+(?:\.\d+)?)\s*(kg|kilos?|g|gr|gramos?|l|lt|lts|litros?|ml|cc)\b/g))
  if (!matches.length) return null

  const match = matches[matches.length - 1]
  const amount = Number(match[1])
  const unitInfo = normalizeUnit(match[2])
  if (!unitInfo || Number.isNaN(amount)) return null

  return {
    amount: amount * unitInfo.factor,
    family: unitInfo.family,
    label: formatSize({ amount: amount * unitInfo.factor, family: unitInfo.family }),
  }
}

function extractProductSize(product) {
  const fromName = extractSizeFromText(product?.name)
  if (fromName) return fromName

  const fromContent = extractSizeFromText(`${product?.net_content ?? ''} ${product?.unit ?? ''}`)
  if (fromContent) return fromContent

  return null
}

function parseCartLine(value) {
  const raw = String(value ?? '').trim()
  const targetSize = extractSizeFromText(raw)
  const searchTerm = raw
    .replace(/(\d+(?:[.,]\d+)?)\s*(kg|kilos?|g|gr|gramos?|l|lt|lts|litros?|ml|cc)\b/gi, '')
    .replace(/\s+/g, ' ')
    .trim()

  return {
    raw,
    searchTerm: searchTerm || raw,
    targetSize,
  }
}

function productMatchesQuery(product, query) {
  const haystack = normalizeText(product?.name)
  return normalizeText(query)
    .split(/\s+/)
    .filter(Boolean)
    .every((token) => haystack.includes(token))
}

function estimateComparablePrice(product, targetSize) {
  const productPrice = priceNumber(product?.price)
  const productSize = extractProductSize(product)

  if (!Number.isFinite(productPrice)) {
    return {
      productSize,
      estimatedPrice: Number.POSITIVE_INFINITY,
      comparable: false,
    }
  }

  if (!targetSize || !productSize || targetSize.family !== productSize.family || productSize.amount <= 0) {
    return {
      productSize,
      estimatedPrice: productPrice,
      comparable: false,
    }
  }

  return {
    productSize,
    estimatedPrice: productPrice * (targetSize.amount / productSize.amount),
    comparable: true,
  }
}

function Pill({ children }) {
  return <span className="rounded-full bg-[#f8e4df] px-3 py-1 text-xs font-semibold text-[#8f4b62]">{children}</span>
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
  const [expanded, setExpanded] = useState(false)

  if (!items.length) return <Muted>Sin detalle disponible</Muted>

  const visible = expanded ? items : items.slice(0, limit)
  const remaining = items.length - visible.length

  return (
    <div className="flex max-w-[520px] flex-wrap gap-1.5">
      {visible.map((item) => (
        <span key={item} className="rounded-md bg-slate-100 px-2 py-1 text-xs text-slate-700">
          {item}
        </span>
      ))}
      {remaining > 0 ? (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="rounded-md bg-emerald-100 px-2 py-1 text-xs font-semibold text-emerald-800 transition hover:bg-emerald-200"
        >
          Ver {remaining} más
        </button>
      ) : expanded && items.length > limit ? (
        <button
          type="button"
          onClick={() => setExpanded(false)}
          className="rounded-md bg-slate-200 px-2 py-1 text-xs font-semibold text-slate-700 transition hover:bg-slate-300"
        >
          Ver menos
        </button>
      ) : null}
    </div>
  )
}

function parseCartText(value) {
  return Array.from(
    new Set(
      String(value ?? '')
        .split(/[\n,;]+/)
        .map((item) => item.trim())
        .filter(Boolean),
    ),
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
  const [cartText, setCartText] = useState('arroz basmati 1 kg\nleche entera 1 L\naceite vegetal 1 L')
  const [cartRows, setCartRows] = useState([])
  const [cartLoading, setCartLoading] = useState(false)
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
      const results = await searchProducts(query, market, 30)
      setSearchResult(results.items ?? [])
    } catch (err) {
      setError(err.message)
    } finally {
      setSearching(false)
    }
  }

  function addCartTerm(term) {
    const cleanTerm = String(term ?? '').trim()
    if (!cleanTerm) return

    const current = parseCartText(cartText)
    if (!current.some((item) => item.toLowerCase() === cleanTerm.toLowerCase())) {
      setCartText([...current, cleanTerm].join('\n'))
    }
  }

  function removeCartTerm(term) {
    const nextItems = parseCartText(cartText).filter((item) => item.toLowerCase() !== term.toLowerCase())
    setCartText(nextItems.join('\n'))
    setCartRows((rows) => rows.filter((row) => row.query.toLowerCase() !== term.toLowerCase()))
  }

  async function buildCart(event) {
    event?.preventDefault()
    const items = parseCartText(cartText).map(parseCartLine)
    if (!items.length) {
      setCartRows([])
      return
    }

    const supermarkets = metadata?.supermarkets?.length ? metadata.supermarkets : ['jumbo', 'lider', 'unimarc']

    try {
      setCartLoading(true)
      const rows = await Promise.all(
        items.map(async (item) => {
          const result = await searchProducts(item.searchTerm, '', 500)
          const marketResults = Object.fromEntries(
            supermarkets.map((supermarket) => {
              let options = (result.items ?? [])
                .filter((product) => String(product.supermarket ?? '').toLowerCase() === supermarket.toLowerCase())
                .filter((product) => productMatchesQuery(product, item.searchTerm))
                .map((product) => ({
                  product,
                  ...estimateComparablePrice(product, item.targetSize),
                }))

              if (item.targetSize && options.some((option) => option.comparable)) {
                options = options.filter((option) => option.comparable)
              }

              options = options.sort((a, b) => a.estimatedPrice - b.estimatedPrice)

              return [supermarket, options[0] ?? null]
            }),
          )

          const available = Object.entries(marketResults)
            .filter(([, option]) => option)
            .map(([supermarket, option]) => ({
              supermarket,
              product: option.product,
              price: option.estimatedPrice,
            }))
            .filter((itemPrice) => Number.isFinite(itemPrice.price))

          const cheapest = available.sort((a, b) => a.price - b.price)[0] ?? null

          return {
            query: item.raw,
            searchTerm: item.searchTerm,
            targetSize: item.targetSize,
            markets: marketResults,
            cheapestMarket: cheapest?.supermarket ?? null,
            cheapestPrice: cheapest?.price ?? null,
          }
        }),
      )

      setCartRows(rows)
    } catch (err) {
      setError(err.message)
    } finally {
      setCartLoading(false)
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
  const supermarketNames = metadata?.supermarkets?.length ? metadata.supermarkets : ['jumbo', 'lider', 'unimarc']
  const cartItems = parseCartText(cartText)
  const cartTotals = supermarketNames.map((supermarket) => {
    const prices = cartRows
      .map((row) => row.markets?.[supermarket])
      .filter(Boolean)
      .map((option) => option.estimatedPrice)
      .filter((price) => Number.isFinite(price))

    return {
      supermarket,
      total: prices.reduce((sum, price) => sum + price, 0),
      found: prices.length,
      expected: cartRows.length,
    }
  })
  const lowestCartTotal = Math.min(...cartTotals.filter((item) => item.found === item.expected).map((item) => item.total))

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
      {
        key: 'cart',
        label: 'Carrito',
        render: (_value, row) => (
          <button
            type="button"
            onClick={() => addCartTerm(row.name)}
            className="inline-flex items-center gap-1 rounded-lg bg-emerald-600 px-3 py-2 text-xs font-bold text-white transition hover:bg-emerald-700"
          >
            <Plus className="h-3.5 w-3.5" />
            Agregar
          </button>
        ),
      },
    ],
    [cartText],
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

  const cbaDriverColumns = [
    { key: 'supermarket', label: 'Supermercado', render: (value) => <Pill>{value}</Pill> },
    { key: 'cba_name', label: 'Ítem CBA' },
    { key: 'estimated_month_cost', label: 'Costo usado', render: formatCurrency },
    { key: 'name', label: 'Producto detectado' },
    { key: 'brand', label: 'Marca', render: formatBrand },
  ]

  return (
    <main className="min-h-screen bg-soft text-ink">
      <section className="bg-gradient-to-br from-ocean via-plum to-brand px-4 py-10 text-white sm:px-6 lg:px-8">
        <div className="mx-auto max-w-7xl">
          <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
            <div className="max-w-3xl">
              <h1 className="text-4xl font-black tracking-tight sm:text-5xl">
                Comparador de precios de supermercados
              </h1>
            </div>
            <div className="rounded-3xl bg-white/15 p-5 backdrop-blur">
              <p className="text-sm text-white/80">Fuente de datos</p>
              <p className="mt-1 text-2xl font-bold">{health?.status === 'ok' ? dataModeLabel : 'Pendiente'}</p>
              <p className="mt-2 text-sm text-white/80">
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
            helper={latestConsolidado ? 'Base consolidada disponible' : 'Ejecuta extraccion_limpieza.py para actualizar'}
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
        </SectionCard>

        <SectionCard
          title="Armar carrito y comparar"
          description="Escribe producto, tipo y formato objetivo, por ejemplo: arroz basmati 1 kg, leche entera 1 L, aceite vegetal 900 ml. Con esa información la comparación evita mezclar envases o productos parecidos."
        >
          <form onSubmit={buildCart} className="grid gap-4 lg:grid-cols-[minmax(280px,0.8fr)_1.2fr]">
            <div className="space-y-3">
              <textarea
                value={cartText}
                onChange={(event) => setCartText(event.target.value)}
                className="min-h-[170px] w-full rounded-2xl border border-slate-300 bg-white p-4 text-sm outline-none transition focus:border-emerald-500 focus:ring-4 focus:ring-emerald-100"
                placeholder="Un producto por línea: arroz basmati 1 kg, leche entera 1 L, aceite vegetal 900 ml..."
              />
              <div className="flex flex-wrap gap-2">
                {cartItems.map((item) => (
                  <button
                    key={item}
                    type="button"
                    onClick={() => removeCartTerm(item)}
                    className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-700 transition hover:bg-red-50 hover:text-red-700"
                  >
                    {item}
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                ))}
              </div>
              <button
                type="submit"
                disabled={cartLoading}
                className="inline-flex w-full items-center justify-center gap-2 rounded-2xl bg-brand px-5 py-3 font-bold text-white transition hover:bg-brandDark disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto"
              >
                <ShoppingCart className="h-4 w-4" />
                {cartLoading ? 'Comparando...' : 'Comparar carrito'}
              </button>
            </div>

            <div className="overflow-hidden rounded-2xl border border-slate-200">
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-slate-200 text-sm">
                  <thead className="bg-slate-50">
                    <tr>
                      <th className="whitespace-nowrap px-4 py-3 text-left font-semibold text-slate-700">Producto buscado</th>
                      {supermarketNames.map((supermarket) => (
                        <th key={supermarket} className="whitespace-nowrap px-4 py-3 text-left font-semibold capitalize text-slate-700">
                          {supermarket}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 bg-white">
                    {cartRows.length ? (
                      cartRows.map((row) => (
                        <tr key={row.query}>
                          <td className="px-4 py-3 align-top">
                            <p className="font-semibold text-ink">{row.searchTerm}</p>
                            <p className="mt-1 text-xs text-slate-500">
                              Objetivo: {row.targetSize ? formatSize(row.targetSize) : 'sin formato'}
                            </p>
                          </td>
                          {supermarketNames.map((supermarket) => {
                            const option = row.markets?.[supermarket]
                            const product = option?.product
                            const isLowest = row.cheapestMarket === supermarket

                            return (
                              <td
                                key={supermarket}
                                className={`min-w-[230px] px-4 py-3 align-top ${
                                  isLowest ? 'bg-emerald-50 text-emerald-950' : 'text-slate-700'
                                }`}
                              >
                                {product ? (
                                  <div>
                                    <div className="flex items-center gap-2">
                                      <span className="font-bold">
                                        {option.comparable ? formatCurrency(option.estimatedPrice) : formatCurrency(product.price)}
                                      </span>
                                      {isLowest ? (
                                        <span className="rounded-full bg-emerald-600 px-2 py-0.5 text-[11px] font-bold text-white">
                                          menor
                                        </span>
                                      ) : null}
                                    </div>
                                    <p className="mt-1 text-xs font-medium text-slate-500">
                                      {option.comparable
                                        ? `Estimado para ${formatSize(row.targetSize)} · envase ${formatSize(option.productSize)}`
                                        : `Envase ${formatSize(option.productSize)} · sin equivalencia`}
                                    </p>
                                    {option.comparable ? (
                                      <p className="mt-1 text-xs text-slate-400">Precio envase: {formatCurrency(product.price)}</p>
                                    ) : null}
                                    <p className="mt-1 max-w-[260px] text-xs leading-snug">{product.name}</p>
                                    <p className="mt-1 text-xs text-slate-400">{product.brand || 'Marca no informada'}</p>
                                  </div>
                                ) : (
                                  <Muted>Sin resultado</Muted>
                                )}
                              </td>
                            )
                          })}
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={supermarketNames.length + 1} className="px-4 py-8 text-center text-muted">
                          Presiona “Comparar carrito” para ver precios por supermercado.
                        </td>
                      </tr>
                    )}
                  </tbody>
                  {cartRows.length ? (
                    <tfoot className="bg-slate-50">
                      <tr>
                        <td className="px-4 py-3 font-bold text-ink">Total productos encontrados</td>
                        {cartTotals.map((item) => {
                          const isLowestTotal = item.found === item.expected && item.total === lowestCartTotal

                          return (
                            <td
                              key={item.supermarket}
                              className={`px-4 py-3 font-bold ${
                                isLowestTotal ? 'bg-emerald-100 text-emerald-950' : 'text-slate-700'
                              }`}
                            >
                              <div>{item.found ? formatCurrency(item.total) : '—'}</div>
                              <div className="mt-1 text-xs font-medium text-slate-500">
                                {item.found} de {item.expected} productos
                              </div>
                            </td>
                          )
                        })}
                      </tr>
                    </tfoot>
                  ) : null}
                </table>
              </div>
            </div>
          </form>
        </SectionCard>

        <SectionCard
          title="Resumen CBA por supermercado"
          description="Costo estimado para los ítems CBA detectados. Si la diferencia entre supermercados parece demasiado alta, revisa abajo los productos que más explican el costo: ahí se ven posibles matches débiles o formatos poco comparables."
        >
          <DataTable columns={cbaColumns} rows={cba?.resumen_supermercado ?? []} />
        </SectionCard>

        <SectionCard
          title="Por qué cambia tanto el costo CBA"
          description="Estos son los ítems con mayor costo usado en el cálculo. Sirven para auditar si el producto detectado realmente corresponde al ítem CBA."
        >
          <DataTable columns={cbaDriverColumns} rows={cba?.cost_drivers ?? []} />
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
