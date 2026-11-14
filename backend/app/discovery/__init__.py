"""Discovery: finding possible copies of protected images (phase 4).

- providers.py  the DiscoveryProvider interface + implementations
- fetch.py      the only way the server touches the web (SSRF-safe, polite)
- parse.py      extracting image URLs from an HTML page
- matching.py   fingerprinting candidates in memory and comparing them
- jobs.py       running a discovery job end to end
- worker.py     the background loop that runs queued jobs

Candidate images are processed in memory and NEVER stored (13.11).
"""
