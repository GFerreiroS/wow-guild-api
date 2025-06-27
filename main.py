from fastapi import FastAPI, HTTPException

import lib.wow as wow

app = FastAPI(
    title="Blizzard API",
    description="A simple API to fetch data from Blizzard's API using OAuth2.",
    version="1.0.0",
    docs_url="/docs",
)


@app.get("/token")
def read_token():
    price_copper = int(wow.get_wow_token())
    price_gold = price_copper // 10000
    try:
        return {"price": f"{price_gold:,}"}
    except Exception as e:
        raise HTTPException(502, str(e))


@app.get("/guild")
def read_guild():
    try:
        return wow.get_guild_info()
    except Exception as e:
        raise HTTPException(502, str(e))
