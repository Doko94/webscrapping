const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
const DATA_MODE = import.meta.env.VITE_DATA_MODE ?? 'api'

let productsIndexCache = null

async function request(path) {
  const response = await fetch(`${API_BASE_URL}${path}`)

  if (!response.ok) {
    throw new Error(`Error API ${response.status}: ${response.statusText}`)
  }

  return response.json()
}

async function requestStatic(fileName) {
  const response = await fetch(`/data/${fileName}`)

  if (!response.ok) {
    throw new Error(`No se pudo leer /data/${fileName}`)
  }

  return response.json()
}

function normalizeText(value) {
  return String(value ?? '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim()
}

function priceNumber(value) {
  const parsed = Number(String(value ?? '').replace(/\./g, '').replace(',', '.'))
  return Number.isNaN(parsed) ? Number.POSITIVE_INFINITY : parsed
}

async function getProductsIndex() {
  if (!productsIndexCache) {
    productsIndexCache = await requestStatic('products_index.json')
  }
  return productsIndexCache
}

export function getHealth() {
  if (DATA_MODE === 'static') return requestStatic('health.json')
  return request('/health')
}

export function getDataMode() {
  return DATA_MODE
}

export function getDataMode() {
  return DATA_MODE
}

export function getMetadata() {
  if (DATA_MODE === 'static') return requestStatic('metadata.json')
  return request('/metadata')
}

export function getProductSummary() {
  if (DATA_MODE === 'static') return requestStatic('products_summary.json')
  return request('/products/summary')
}

export async function searchProducts(query, supermarket = '', limit = 30) {
  if (DATA_MODE === 'static') {
    const normalizedQuery = normalizeText(query)
    const normalizedMarket = normalizeText(supermarket)
    const rows = await getProductsIndex()

    const items = rows
      .filter((item) => {
        if (normalizedMarket && normalizeText(item.supermarket) !== normalizedMarket) return false

        const haystack = [
          item.name,
          item.brand,
          item.category,
          item.subcategory,
          item.last_category,
          item.category_std,
        ]
          .map(normalizeText)
          .join(' ')

        return haystack.includes(normalizedQuery)
      })
      .sort((a, b) => priceNumber(a.price) - priceNumber(b.price))
      .slice(0, limit)

    return { query, items }
  }

  const params = new URLSearchParams({ q: query, limit: String(limit) })
  if (supermarket) params.set('supermarket', supermarket)
  return request(`/products/search?${params.toString()}`)
}

export async function compareProduct(query) {
  if (DATA_MODE === 'static') {
    const { items } = await searchProducts(query, '', 200)
    const grouped = new Map()

    items.forEach((item) => {
      const market = item.supermarket ?? 'sin supermercado'
      if (!grouped.has(market)) grouped.set(market, [])
      grouped.get(market).push(item)
    })

    return {
      query,
      markets: Array.from(grouped.entries()).map(([supermarket, marketItems]) => ({
        supermarket,
        items: marketItems.slice(0, 5),
      })),
    }
  }

  const params = new URLSearchParams({ q: query })
  return request(`/products/compare?${params.toString()}`)
}

export function getCbaSummary() {
  if (DATA_MODE === 'static') return requestStatic('cba_summary.json')
  return request('/cba/summary')
}

export function getEconomicScenario() {
  if (DATA_MODE === 'static') return requestStatic('scenarios_economic.json')
  return request('/scenarios/economic')
}

export function getPremiumScenario() {
  if (DATA_MODE === 'static') return requestStatic('scenarios_premium.json')
  return request('/scenarios/premium')
}

export function getCartSummary() {
  if (DATA_MODE === 'static') return requestStatic('cart_summary.json')
  return request('/cart/summary')
}
