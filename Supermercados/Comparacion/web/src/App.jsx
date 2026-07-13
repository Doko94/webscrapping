import { useEffect, useState } from 'react'
import { ExternalLink, ShoppingCart, Trash2 } from 'lucide-react'

import {
  getCbaSummary,
  getEconomicScenario,
  getMetadata,
  getPremiumScenario,
  searchProducts,
} from './api'
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

function listPriceNumber(product) {
  const listPrice = priceNumber(product?.list_price)
  if (Number.isFinite(listPrice) && listPrice > 0) return listPrice
  return priceNumber(product?.price)
}

function referencePriceNumber(product) {
  const detectedPrice = priceNumber(product?.price)
  const listPrice = priceNumber(product?.list_price)

  if (!Number.isFinite(detectedPrice) || detectedPrice <= 0) return listPrice
  if (!Number.isFinite(listPrice) || listPrice <= 0) return detectedPrice

  const ratio = detectedPrice / listPrice
  return ratio <= 0.25 ? listPrice : detectedPrice
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

function getProductLink(product) {
  return product?.detail_url ?? product?.link ?? product?.url ?? product?.product_url ?? null
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
  const productPrice = referencePriceNumber(product)
  const detectedPrice = priceNumber(product?.price)
  const listPrice = priceNumber(product?.list_price)
  const productSize = extractProductSize(product)

  if (!Number.isFinite(productPrice)) {
    return {
      productSize,
      estimatedPrice: Number.POSITIVE_INFINITY,
      detectedPrice,
      listPrice,
      estimatedDetectedPrice: Number.POSITIVE_INFINITY,
      estimatedListPrice: Number.POSITIVE_INFINITY,
      comparable: false,
    }
  }

  if (!targetSize || !productSize || targetSize.family !== productSize.family || productSize.amount <= 0) {
    return {
      productSize,
      estimatedPrice: productPrice,
      detectedPrice,
      listPrice,
      estimatedDetectedPrice: detectedPrice,
      estimatedListPrice: listPrice,
      comparable: false,
    }
  }

  return {
    productSize,
    estimatedPrice: productPrice * (targetSize.amount / productSize.amount),
    detectedPrice,
    listPrice,
    estimatedDetectedPrice: Number.isFinite(detectedPrice) ? detectedPrice * (targetSize.amount / productSize.amount) : Number.POSITIVE_INFINITY,
    estimatedListPrice: Number.isFinite(listPrice) ? listPrice * (targetSize.amount / productSize.amount) : Number.POSITIVE_INFINITY,
    comparable: true,
  }
}

function formatItemsCoverage(found, total, formattedPct) {
  if (found === null || found === undefined || total === null || total === undefined) return '—'
  return `${Number(found).toLocaleString('es-CL')} de ${Number(total).toLocaleString('es-CL')} (${formattedPct ?? '—'})`
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

function RecommendationCard({ label, market, amount, helper, tone = 'default' }) {
  const toneClass = tone === 'primary' ? 'border-brand bg-[#fff3f0]' : 'border-[#ead9d7] bg-white/90'

  return (
    <article className={`rounded-2xl border p-5 shadow-soft ${toneClass}`}>
      <p className="text-sm font-semibold text-plum">{label}</p>
      <div className="mt-3 flex items-end justify-between gap-3">
        <p className="text-3xl font-black capitalize tracking-tight text-ink">{market ?? '—'}</p>
        <p className="text-lg font-bold text-brand">{amount ?? '—'}</p>
      </div>
      {helper ? <p className="mt-3 text-sm leading-relaxed text-muted">{helper}</p> : null}
    </article>
  )
}

export default function App() {
  const [metadata, setMetadata] = useState(null)
  const [cba, setCba] = useState(null)
  const [economic, setEconomic] = useState(null)
  const [premium, setPremium] = useState(null)
  const [cartText, setCartText] = useState('arroz basmati 1 kg\nleche entera 1 L\naceite vegetal 1 L')
  const [cartRows, setCartRows] = useState([])
  const [cartLoading, setCartLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    async function loadInitialData() {
      try {
        const [metadataData, cbaData, economicData, premiumData] = await Promise.all([
          getMetadata(),
          getCbaSummary(),
          getEconomicScenario(),
          getPremiumScenario(),
        ])

        setMetadata(metadataData)
        setCba(cbaData)
        setEconomic(economicData)
        setPremium(premiumData)
      } catch (err) {
        setError(err.message)
      }
    }

    loadInitialData()
  }, [])

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

  const bestCbaMarket = cba?.resumen_supermercado?.[0]
  const bestEconomic = economic?.total_por_supermercado?.[0]
  const bestPremium = premium?.total_por_supermercado?.[0]
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

  return (
    <main className="min-h-screen bg-soft text-ink">
      <section className="bg-gradient-to-br from-ocean via-plum to-brand px-4 py-8 text-white sm:px-6 lg:px-8">
        <div className="mx-auto max-w-7xl">
          <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
            <div className="max-w-3xl">
              <h1 className="text-3xl font-black tracking-tight sm:text-5xl">
                Comparador de precios de supermercados
              </h1>
              <p className="mt-4 max-w-2xl text-base leading-relaxed text-white/85 sm:text-lg">
                Esta herramienta compara precios reales detectados en supermercados y resume dónde conviene comprar según cuatro miradas: canasta básica, compra económica, selección premium y tu propio carrito.
              </p>
            </div>
          </div>
        </div>
      </section>

      <div className="mx-auto max-w-7xl space-y-6 px-3 py-6 sm:space-y-8 sm:px-6 sm:py-8 lg:px-8">
        {error ? (
          <div className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            {error}
          </div>
        ) : null}

        <section className="grid gap-4 lg:grid-cols-3">
          <RecommendationCard
            label="Conviene por CBA"
            market={bestCbaMarket?.supermarket}
            amount={bestCbaMarket ? formatCurrency(bestCbaMarket.costo_total_cba_detectada) : null}
            helper={bestCbaMarket ? `${formatItemsCoverage(bestCbaMarket.cba_items_cubiertos, bestCbaMarket.cba_items_totales, bestCbaMarket.cobertura_pct_fmt)} de la canasta detectada.` : 'Sin resumen CBA'}
            tone="primary"
          />
          <RecommendationCard
            label="Conviene en económico"
            market={bestEconomic?.supermarket}
            amount={bestEconomic ? formatCurrency(bestEconomic.total_cba_economica) : null}
            helper={bestEconomic ? `${formatItemsCoverage(bestEconomic.productos_encontrados, bestEconomic.productos_cba_objetivo, bestEconomic.cobertura_pct_fmt)} con criterio de menor precio.` : 'Sin datos'}
          />
          <RecommendationCard
            label="Conviene en premium"
            market={bestPremium?.supermarket}
            amount={bestPremium ? formatCurrency(bestPremium.total_cba_premium) : null}
            helper={bestPremium ? `${formatItemsCoverage(bestPremium.productos_encontrados, bestPremium.productos_cba_objetivo, bestPremium.cobertura_pct_fmt)} con selección más estricta.` : 'Sin datos'}
          />
        </section>

        <SectionCard
          title="Armar carrito y comparar"
          description="Ingresa tu lista de compra con formato objetivo. La vista estima precios comparables por supermercado y destaca la alternativa más conveniente para cada producto."
        >
          <form onSubmit={buildCart} className="space-y-4">
            <div className="max-w-3xl space-y-3">
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

            <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
              <div className="divide-y divide-slate-100">
                {cartRows.length ? (
                  cartRows.map((row) => (
                    <article key={`${row.query}-mobile`} className="p-4">
                      <div className="mb-3">
                        <p className="font-bold text-ink">{row.searchTerm}</p>
                        <p className="mt-1 text-xs text-slate-500">
                          Objetivo: {row.targetSize ? formatSize(row.targetSize) : 'sin formato'}
                        </p>
                      </div>
                      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                        {supermarketNames.map((supermarket) => {
                          const option = row.markets?.[supermarket]
                          const product = option?.product
                          const productLink = getProductLink(product)
                          const isLowest = row.cheapestMarket === supermarket

                          return (
                            <div
                              key={supermarket}
                              className={`rounded-xl border p-3 ${
                                isLowest ? 'border-emerald-700 bg-emerald-100' : 'border-slate-200 bg-white'
                              }`}
                            >
                              <div className="flex items-start justify-between gap-3">
                                <p className="font-bold capitalize text-ink">{supermarket}</p>
                                {product ? (
                                  <div className="text-right">
                                    <p className="font-black text-ink">
                                      {option.comparable ? formatCurrency(option.estimatedPrice) : formatCurrency(referencePriceNumber(product))}
                                    </p>
                                    {isLowest ? (
                                      <span className="mt-1 inline-flex rounded-full bg-emerald-900 px-2 py-0.5 text-[11px] font-bold text-white">
                                        menor
                                      </span>
                                    ) : null}
                                  </div>
                                ) : null}
                              </div>
                              {product ? (
                                <div className="mt-2 text-xs text-slate-600">
                                  <p className="font-medium text-slate-700">{product.name}</p>
                                  <p className="mt-1">
                                    {option.comparable
                                      ? `Estimado para ${formatSize(row.targetSize)} · envase ${formatSize(option.productSize)}`
                                      : `Envase ${formatSize(option.productSize)} · sin equivalencia`}
                                  </p>
                                  <p className="mt-1 text-slate-400">Precio usado envase: {formatCurrency(referencePriceNumber(product))}</p>
                                  {Number.isFinite(option.listPrice) && option.listPrice !== referencePriceNumber(product) ? (
                                    <p className="mt-1 text-slate-400">
                                      Precio lista informado: {formatCurrency(option.listPrice)}
                                      {option.comparable && Number.isFinite(option.estimatedListPrice)
                                        ? ` · estimado ${formatCurrency(option.estimatedListPrice)}`
                                        : ''}
                                    </p>
                                  ) : null}
                                  {Number.isFinite(option.detectedPrice) && option.detectedPrice !== referencePriceNumber(product) ? (
                                    <p className="mt-1 text-slate-400">
                                      Precio detectado/oferta: {formatCurrency(option.detectedPrice)}
                                      {option.comparable && Number.isFinite(option.estimatedDetectedPrice)
                                        ? ` · estimado ${formatCurrency(option.estimatedDetectedPrice)}`
                                        : ''}
                                    </p>
                                  ) : null}
                                  <p className="mt-1 flex flex-wrap items-center gap-1 text-slate-500">
                                    <span className="font-semibold text-slate-600">Link:</span>
                                    {productLink ? (
                                      <a
                                        href={productLink}
                                        target="_blank"
                                        rel="noreferrer"
                                        className="inline-flex items-center gap-1 font-semibold text-brand underline-offset-2 hover:text-brandDark hover:underline"
                                      >
                                        Ver producto
                                        <ExternalLink className="h-3 w-3" />
                                      </a>
                                    ) : (
                                      <span>No disponible</span>
                                    )}
                                  </p>
                                </div>
                              ) : (
                                <p className="mt-2 text-sm text-slate-400">Sin resultado</p>
                              )}
                            </div>
                          )
                        })}
                      </div>
                    </article>
                  ))
                ) : (
                  <div className="p-8 text-center text-sm text-muted">
                    Presiona “Comparar carrito” para ver precios por supermercado.
                  </div>
                )}

                {cartRows.length ? (
                  <div className="bg-[#fbf0ed] p-4">
                    <p className="mb-3 font-bold text-ink">Total productos encontrados</p>
                    <div className="grid gap-2 md:grid-cols-3">
                      {cartTotals.map((item) => {
                        const isLowestTotal = item.found === item.expected && item.total === lowestCartTotal

                        return (
                          <div
                            key={item.supermarket}
                            className={`flex items-center justify-between rounded-xl px-3 py-2 ${
                              isLowestTotal ? 'bg-emerald-800 text-white ring-1 ring-emerald-950' : 'bg-white text-slate-700'
                            }`}
                          >
                            <span className="font-bold capitalize">{item.supermarket}</span>
                            <span className="text-right">
                              <span className="block font-black">{item.found ? formatCurrency(item.total) : '—'}</span>
                              <span className="text-xs">{item.found} de {item.expected} productos</span>
                            </span>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                ) : null}
              </div>
            </div>
          </form>
        </SectionCard>
      </div>
    </main>
  )
}
