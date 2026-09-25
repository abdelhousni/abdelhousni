"""Rebuild the dynamic sections of README.md.

Adapted from https://github.com/simonw/simonw - see
https://simonwillison.net/2020/Jul/10/self-updating-profile-readme/
"""
import os
import pathlib
import re

import feedparser
import httpx

root = pathlib.Path(__file__).parent.resolve()

OWNER = "abdelhousni"
TIL_FEED = "https://abdelhousni.github.io/til/feed.atom"
TOKEN = os.environ.get("GH_TOKEN", "")

GRAPHQL_QUERY = """
query($query: String!, $after: String) {
  search(first: 100, type: REPOSITORY, query: $query, after: $after) {
    pageInfo { hasNextPage endCursor }
    nodes {
      ... on Repository {
        name
        url
        releases(orderBy: {field: CREATED_AT, direction: DESC}, first: 1) {
          nodes { name tagName publishedAt url }
        }
      }
    }
  }
}
"""


def replace_chunk(content, marker, chunk):
    r = re.compile(
        r"<!\-\- {} starts \-\->.*<!\-\- {} ends \-\->".format(marker, marker),
        re.DOTALL,
    )
    chunk = "<!-- {} starts -->\n{}\n<!-- {} ends -->".format(marker, chunk, marker)
    return r.sub(lambda m: chunk, content)


def fetch_releases():
    releases = []
    after = None
    while True:
        response = httpx.post(
            "https://api.github.com/graphql",
            json={
                "query": GRAPHQL_QUERY,
                "variables": {"query": "user:{} is:public".format(OWNER), "after": after},
            },
            headers={"Authorization": "Bearer {}".format(TOKEN)},
            timeout=30,
        )
        response.raise_for_status()
        search = response.json()["data"]["search"]
        for repo in search["nodes"]:
            nodes = (repo.get("releases") or {}).get("nodes") or []
            if not nodes or not nodes[0]["publishedAt"]:
                continue
            release = nodes[0]
            name = (release["name"] or release["tagName"]).replace(repo["name"], "").strip()
            releases.append(
                {
                    "repo": repo["name"],
                    "release": name or release["tagName"],
                    "url": release["url"],
                    "published_at": release["publishedAt"],
                    "published_day": release["publishedAt"].split("T")[0],
                }
            )
        if not search["pageInfo"]["hasNextPage"]:
            break
        after = search["pageInfo"]["endCursor"]
    releases.sort(key=lambda r: r["published_at"], reverse=True)
    return releases


def fetch_tils():
    entries = feedparser.parse(TIL_FEED)["entries"]
    return [
        {
            "title": entry["title"].replace("_", r"\_"),
            "url": entry["link"],
            "updated": entry["updated"].split("T")[0],
        }
        for entry in entries
    ]


if __name__ == "__main__":
    readme = root / "README.md"
    content = readme.read_text()

    releases = fetch_releases()[:8]
    releases_md = "\n\n".join(
        "[{repo} {release}]({url}) - {published_day}".format(**r) for r in releases
    ) or "_No releases yet._"
    content = replace_chunk(content, "recent_releases", releases_md)

    tils_md = "\n\n".join(
        "[{title}]({url}) - {updated}".format(**t) for t in fetch_tils()[:8]
    )
    content = replace_chunk(content, "tils", tils_md)

    readme.write_text(content)
