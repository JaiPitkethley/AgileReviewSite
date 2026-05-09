const TMDB_API_KEY = "ac9052cb2ef122c333a96cb6540a5e2b";
const IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w342";

async function fetchSeries(query) {
  const url = `https://api.themoviedb.org/3/search/tv?api_key=${TMDB_API_KEY}&query=${encodeURIComponent(query)}&include_adult=false&language=en-US&page=1`;

  const response = await fetch(url);

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

            <button class="btn-primary add-watchlist-btn" data-series-id="${series.id}">
              Add to Watchlist
            </button>
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

      const grid = document.getElementById("topbarSearchResults");

      if (grid) {
        grid.innerHTML = "<p>Something went wrong. Please try again.</p>";
      }
    });
}