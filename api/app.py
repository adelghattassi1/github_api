import asyncio
import time
from aiohttp import web
import aiohttp
import urllib.parse as urlparse
from urllib.parse import parse_qs
from decouple import config

API_KEY = config('API_KEY')
GITHUB_API_URL = config('GITHUB_API_URL')


class GithubApi:
    def __init__(self, api_key):
        self.api_key = api_key

    def get_headers(self):
        return {"Authorization": f"token {self.api_key}"}

    async def handle(self, request):
        start_time = time.time()
        users_response = []
        new_usernames = []
        parsed = urlparse.urlparse(str(request.url))
        usernames = parse_qs(parsed.query).get("usernames")
        commit_latest = parse_qs(parsed.query).get("include")
        if usernames:
            new_usernames = usernames[0].split(",")
        for i, user in enumerate(new_usernames):
            url = GITHUB_API_URL + "/" + user
            async with aiohttp.ClientSession() as session:

                async with session.get(
                        url, headers=self.get_headers(), ssl=False
                ) as response:
                    response_obj = await response.json()
                    tasks = self.gather_repos_endpoints(response_obj, session, commit_latest)
                    results = await asyncio.gather(*tasks)
                    expected_response = {
                        "Login name": response_obj["login"],
                        "User ID": response_obj["id"],
                        "Resource URI": response_obj["html_url"],
                        "Public repositories": results

                    }
                    users_response.append(expected_response)

        print("--- %s seconds ---" % (time.time() - start_time))

        return web.json_response(users_response, status=200)

    async def get_repos_info(self, url, session, commit_latest):
        repos_response = []
        results = []
        repos_url = f"{url}?per_page=1000"
        async with session.get(repos_url, headers=self.get_headers()) as response:
            response_obj = await response.json()
            if commit_latest and "commit_latest" in commit_latest:
                tasks = self.gather_commits_endpoints(response_obj, session)
                results = await asyncio.gather(*tasks)
            for i, repo in enumerate(response_obj):
                expected_resp = {
                    "Repository name": repo["name"],
                    "ID": repo["id"],
                    "Time created": repo["created_at"],
                    "Time updated": repo["updated_at"],
                    "Resource URI": repo["html_url"],
                    "Latest commit": results[i] if results else None,
                }
                repos_response.append(expected_resp)
        return repos_response

    def gather_commits_endpoints(self, response_obj, session):
        tasks = []
        for repo in response_obj:
            task = asyncio.create_task(
                self.get_latest_commit_info(repo["commits_url"], session)
            )
            tasks.append(task)
        return tasks

    def gather_repos_endpoints(self, response_obj, session, commit_latest):
        tasks = []
        for repo in [response_obj]:
            task = asyncio.create_task(
                self.get_repos_info(repo["repos_url"], session, commit_latest)
            )
            tasks.append(task)
        return tasks

    async def get_latest_commit_info(self, commits_url, session):
        commit_dates = []
        commit_uri = commits_url.replace("{/sha}", "")
        async with session.get(commit_uri, headers=self.get_headers()) as response:
            response_obj = await response.json()
            try:
                for commit in response_obj:
                    commit_dates.append(commit["commit"]["committer"]["date"])
                latest_commit = [
                    commit
                    for commit in response_obj
                    if commit["commit"]["committer"]["date"] == max(commit_dates)
                ]
            except:
                pass
            try:
                commit_response = {
                    "Commit hash": latest_commit[0]["sha"],
                    "Author": latest_commit[0]["commit"]["author"]["name"],
                    "committer email": latest_commit[0]["commit"]["committer"]["email"],
                    "Commit date": latest_commit[0]["commit"]["committer"]["date"],
                    "Resource URI": latest_commit[0]["html_url"],
                }
            except:
                commit_response = "No commits"

        return commit_response


app = web.Application()
api = GithubApi(api_key=API_KEY)
app.router.add_get("/users", api.handle)
web.run_app(app, port=8000)
