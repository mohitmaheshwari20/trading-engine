import yfinance as yf

raw = yf.download('^INDIAVIX', start='2024-01-01', end='2024-03-01', progress=False)
print(raw.columns.tolist())
print(raw.head(3))