#!/usr/bin/env python3
"""Refreshes the uptime and the GitHub stats in dark_mode.svg and light_mode.svg.

Runs every day in GitHub Actions (.github/workflows/update.yml). It uses the ACCESS_TOKEN
secret when there is one (so private work counts too) and falls back to the workflow's
own GITHUB_TOKEN, which only sees public repositories.
"""
import datetime as dt
import json
import os
import re
import urllib.request

USER = os.environ.get('USER_NAME', 'schullerlucca')
TOKEN = os.environ.get('ACCESS_TOKEN') or os.environ['GITHUB_TOKEN']
BIRTHDAY = os.environ.get('BIRTHDAY', '2005-11-15')
FILES = ['dark_mode.svg', 'light_mode.svg']

REPOS = '''query($login: String!, $cursor: String) {
  user(login: $login) {
    id
    followers { totalCount }
    repositories(first: 50, after: $cursor, ownerAffiliations: [OWNER, COLLABORATOR, ORGANIZATION_MEMBER]) {
      pageInfo { hasNextPage endCursor }
      nodes { name owner { login } stargazerCount isEmpty }
    }
  }
}'''

HISTORY = '''query($owner: String!, $name: String!, $author: ID!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    defaultBranchRef { target { ... on Commit {
      history(first: 100, after: $cursor, author: {id: $author}) {
        totalCount
        pageInfo { hasNextPage endCursor }
        nodes { additions deletions }
      }
    } } }
  }
}'''


def graphql(query, **variables):
    body = json.dumps({'query': query, 'variables': variables}).encode()
    request = urllib.request.Request('https://api.github.com/graphql', data=body, headers={
        'Authorization': f'bearer {TOKEN}', 'User-Agent': f'{USER}-profile-card'})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = json.load(response)
    if data.get('errors'):
        raise RuntimeError(data['errors'])
    return data['data']


def stats():
    repos, cursor = [], None
    while True:
        user = graphql(REPOS, login=USER, cursor=cursor)['user']
        page = user['repositories']
        repos += page['nodes']
        if not page['pageInfo']['hasNextPage']:
            break
        cursor = page['pageInfo']['endCursor']
    owned = [r for r in repos if r['owner']['login'].lower() == USER.lower()]

    commits = additions = deletions = 0
    for repo in repos:
        if repo['isEmpty']:
            continue
        cursor = None
        while True:
            data = graphql(HISTORY, owner=repo['owner']['login'], name=repo['name'],
                           author=user['id'], cursor=cursor)['repository']
            branch = data and data['defaultBranchRef']
            if not branch:
                break
            history = branch['target']['history']
            if cursor is None:
                commits += history['totalCount']
            for commit in history['nodes']:
                additions += commit['additions']
                deletions += commit['deletions']
            if not history['pageInfo']['hasNextPage']:
                break
            cursor = history['pageInfo']['endCursor']

    return {
        'repo_data': len(owned),
        'contrib_data': len(repos),
        'star_data': sum(r['stargazerCount'] for r in owned),
        'commit_data': commits,
        'follower_data': user['followers']['totalCount'],
        'loc_data': additions - deletions,
        'loc_add': additions,
        'loc_del': deletions,
    }


def uptime(birthday, today):
    years = today.year - birthday.year
    months = today.month - birthday.month
    days = today.day - birthday.day
    if days < 0:
        months -= 1
        days += (today.replace(day=1) - dt.timedelta(days=1)).day
    if months < 0:
        years -= 1
        months += 12

    def unit(n, word):
        return f'{n} {word}' + ('' if n == 1 else 's')

    return f"{unit(years, 'year')}, {unit(months, 'month')}, {unit(days, 'day')}"


def text_of(svg, key):
    match = re.search(rf'<tspan[^>]*\bid="{key}"[^>]*>([^<]*)</tspan>', svg)
    return match.group(1) if match else ''


def update(path, values):
    with open(path, encoding='utf-8') as f:
        svg = f.read()
    for key, text in values.items():
        svg = re.sub(rf'(<tspan[^>]*\bid="{key}"[^>]*>)[^<]*(</tspan>)',
                     lambda m: m.group(1) + text + m.group(2), svg)

    # Each line keeps its width: the dots shrink or grow around the new numbers.
    def pad(match):
        attrs = match.group(1)
        width = int(re.search(r'data-width="(\d+)"', attrs).group(1))
        used = sum(len(text_of(svg, k)) for k in re.search(r'data-for="([^"]+)"', attrs).group(1).split())
        return f'{attrs} {"." * max(1, width - used - 2)} </tspan>'

    svg = re.sub(r'(<tspan[^>]*\bdata-width="\d+"[^>]*>)[^<]*</tspan>', pad, svg)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(svg)


def main():
    values = {key: f'{value:,}' for key, value in stats().items()}
    if BIRTHDAY:
        values['age_data'] = uptime(dt.date.fromisoformat(BIRTHDAY), dt.date.today())
    for path in FILES:
        update(path, values)
    print(values)


if __name__ == '__main__':
    main()
