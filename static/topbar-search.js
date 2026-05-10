const IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w342";

async function fetchSeries(query) {
  const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`);

  if (!response.ok) {
    throw new Error("Failed to fetch TV series");
  }

  const data = await response.json();
  return data.results || [];
}

function renderSeriesResults(seriesList) {
  const discoverContent = document.getElementById("discoverContent");

  if (!discoverContent) {
    console.log("discoverContent not found");
    return;
  }

  let html = `
    <div class="section-header mt-4">
      <span class="section-title">Search Results</span>
      <span class="see-all">View all</span>
    </div>

    <div class="card-grid">
  `;

  if (seriesList.length === 0) {
    html += `<p>No series found.</p>`;
  } else {
    seriesList.forEach(series => {
      const posterUrl = series.poster_path
        ? `${IMAGE_BASE_URL}${series.poster_path}`
        : null;

      const title = series.name || "Unknown Title";

      const year = series.first_air_date
        ? series.first_air_date.substring(0, 4)
        : "Unknown year";

      const rating = series.vote_average
        ? series.vote_average.toFixed(1)
        : "N/A";

      html += `
        <div class="card">
          <div class="poster" style="
            background-image: ${posterUrl ? `url('${posterUrl}')` : "none"};
            background-size: cover;
            background-position: center;
          ">
            ${posterUrl ? "" : title.charAt(0)}
          </div>

          <div class="progress-bar">
            <div class="progress-fill" style="width:0%"></div>
          </div>

          <div class="card-body">
            <div class="card-title">${title}</div>
            <div class="card-sub">
              ${year}
              <div class="stars">⭐ ${rating}</div>
            </div>

            <form action="/watchlist/add" method="post">
              <input type="hidden" name="tmdb_id" value="${series.id}">
              <button type="submit" class="btn-primary add-watchlist-btn">
                Add to Watchlist
              </button>
            </form>
          </div>
        </div>
      `;
    });
  }

  html += `</div>`;

  discoverContent.innerHTML = html;
}

const params = new URLSearchParams(window.location.search);
const query = params.get("q");

if (query) {
  fetchSeries(query)
    .then(seriesList => {
      renderSeriesResults(seriesList);
    })
    .catch(error => {
      console.error(error);

      const discoverContent = document.getElementById("discoverContent");

      if (discoverContent) {
        discoverContent.innerHTML = "<p>Something went wrong. Please try again.</p>";
      }
    });
}