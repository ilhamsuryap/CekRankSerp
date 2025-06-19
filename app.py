from flask import Flask, request, render_template
import requests

app = Flask(__name__)

def get_ranks_serpapi(keyword, domain, hl, gl, google_domain, num):
    api_key = "572db24d1b3554570e4013212f0b26160f44709c398abb0a65dee3428e1ed4e6"
    params = {
        "engine": "google",
        "q": keyword,
        "google_domain": google_domain,
        "hl": hl,
        "gl": gl,
        "num": num,
        "api_key": api_key
    }
    response = requests.get("https://serpapi.com/search", params=params)
    data = response.json()

    ranks = []
    if "organic_results" in data:
        for idx, result in enumerate(data["organic_results"]):
            link = result.get("link", "")
            if domain in link:
                ranks.append({
                    "position": idx + 1,
                    "link": link
                })
    return ranks

@app.route("/", methods=["GET", "POST"])
def index():
    result_data = None
    if request.method == "POST":
        domain = request.form["domain"]
        keyword = request.form["keyword"]
        hl = request.form["hl"]
        gl = request.form["gl"]
        google_domain = request.form["google_domain"]
        num = request.form["num"]

        ranks = get_ranks_serpapi(keyword, domain, hl, gl, google_domain, num)
        result_data = {
            "domain": domain,
            "keyword": keyword,
            "total_found": len(ranks),
            "ranks": ranks
        }

    return render_template("index.html", result=result_data)

if __name__ == "__main__":
    app.run(debug=True)
