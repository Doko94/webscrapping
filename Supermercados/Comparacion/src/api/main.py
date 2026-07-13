from __future__ import annotations

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

try:
    from .services import (
        cart_summary,
        cba_summary,
        compare_product,
        get_health,
        get_metadata,
        product_summary,
        scenario_summary,
        search_products,
    )
except ImportError:
    from services import (
        cart_summary,
        cba_summary,
        compare_product,
        get_health,
        get_metadata,
        product_summary,
        scenario_summary,
        search_products,
    )


app = FastAPI(
    title="API Comparación Supermercados",
    description="API para consultar consolidado, CBA, carrito y escenarios de supermercados.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return get_health()


@app.get("/metadata")
def metadata():
    return get_metadata()


@app.get("/products/summary")
def products_summary():
    return product_summary()


@app.get("/products/search")
def products_search(
    q: str = Query("", description="Texto a buscar, por ejemplo 'leche'. Vacio devuelve el consolidado limitado."),
    supermarket: str | None = Query(None, description="Filtro opcional: jumbo, lider o unimarc"),
    limit: int = Query(30, ge=1, le=100),
):
    return {
        "query": q,
        "items": search_products(q, supermarket=supermarket, limit=limit),
    }


@app.get("/products/compare")
def products_compare(
    q: str = Query(..., min_length=1, description="Texto a comparar por supermercado"),
    limit_per_market: int = Query(5, ge=1, le=20),
):
    return compare_product(q, limit_per_market=limit_per_market)


@app.get("/cba/summary")
def cba():
    return cba_summary()


@app.get("/cart/summary")
def cart():
    return cart_summary()


@app.get("/scenarios/economic")
def economic():
    return scenario_summary("economic")


@app.get("/scenarios/premium")
def premium():
    return scenario_summary("premium")
