import pandas as pd

def build_jumbo_categories(df):
    df["category"] = df.get("categoria")
    df["subcategory"] = None
    df["last_category"] = df.get("subcat_name")
    return df

def build_unimarc_categories(df):
    df["category"] = df.get("categoria")
    df["subcategory"] = df.get("group_name")
    df["last_category"] = df.get("category_name")
    return df

def build_lider_categories(df):
    df["category"] = df.get("categoria")
    df["subcategory"] = df.get("subcat_name")
    df["last_category"] = None
    return df