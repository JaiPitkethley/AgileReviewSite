const TMDB_API_KEY = "ac9052cb2ef122c333a96cb6540a5e2b";
const IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w342";
const RESULTS_PER_PAGE = 6;

function getSavedSeriesIds() {
  return JSON.parse(localStorage.getItem("savedSeriesIds")) || [];
}

function saveSeriesId(seriesId) {
  const savedIds = getSavedSeriesIds();

  if (!savedIds.includes(seriesId)) {
    savedIds.push(seriesId);
  }

  localStorage.setItem("savedSeriesIds", JSON.stringify(savedIds));
}

function removeSeriesId(seriesId) {
  const savedIds = getSavedSeriesIds().filter(id => id !== seriesId);
  localStorage.setItem("savedSeriesIds", JSON.stringify(savedIds));
}

function isSeriesSaved(seriesId) {
  return getSavedSeriesIds().includes(seriesId);
}

async function fetchSeries(query, page = 1) {
  const url = `https://api.themoviedb.org/3/search/tv?api_key=${TMDB_API_KEY}&query=${encodeURIComponent(query)}&include_adult=false&language=en-US&page=${page}`;

  const response = await fetch(url);

  if (!response.ok) {
    throw new Error("Failed to fetch TV series");
  }

  const data = await response.json();
  return {
    results: data.results || [],
    totalPages: data.total_pages || 1,
    page: data.page || 1,
  };
}

function renderSeriesResults(searchData) {
  const resultsContainer = document.getElementById("topbarSearchResults");

  if (!resultsContainer) {
    return;
  }

  const seriesList = searchData.results.slice(0, RESULTS_PER_PAGE);
  const page = searchData.page;
  const totalPages = searchData.totalPages;

  let html = `
    <div class="section-header topbar-search-header">
      <span class="section-title">Search Results</span>
    </div>
    <div class="card-grid topbar-search-card-grid">
  `;

  if (seriesList.length === 0) {
    html += `<p class="search-empty">No series found.</p>`;
  } else {
    seriesList.forEach(series => {
      const posterUrl = series.poster_path
        ? `${IMAGE_BASE_URL}${series.poster_path}`
        : null;

      const title = series.name || "Unknown Title";
      const year = series.first_air_date
        ? series.first_air_date.substring(0, 4)
        : "Unknown";
      const rating = series.vote_average
        ? series.vote_average.toFixed(1)
        : "N/A";

      html += `
        <a class="card series-card-link" href="/series/${series.id}">
          <div class="poster" style="${posterUrl ? `background-image: url('${posterUrl}'); background-size: cover; background-position: center;` : ""}">
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
            <button
              type="button"
              class="btn-primary add-watchlist-btn"
              data-series-id="${series.id}"
            >
              ${isSeriesSaved(String(series.id)) ? "Added" : "Add to Watchlist"}
            </button>
          </div>
        </a>
      `;
    });
  }

  html += `</div>`;

  if (totalPages > 1) {
    html += `
      <div class="pagination-row">
        <button class="pagination-btn" data-page="${Math.max(1, page - 1)}" ${page === 1 ? "disabled" : ""}>Prev</button>
        <span class="pagination-label">Page ${page} of ${totalPages}</span>
        <button class="pagination-btn" data-page="${Math.min(totalPages, page + 1)}" ${page === totalPages ? "disabled" : ""}>Next</button>
      </div>
    `;
  }

  resultsContainer.innerHTML = html;
  resultsContainer.classList.remove("hidden");
}

function showSearchError(message) {
  const resultsContainer = document.getElementById("topbarSearchResults");
  if (!resultsContainer) {
    return;
  }
  resultsContainer.innerHTML = `<p class="search-empty">${message}</p>`;
  resultsContainer.classList.remove("hidden");
}

const params = new URLSearchParams(window.location.search);
const query = params.get("q");
let currentPage = Number(params.get("page") || 1);
let currentQuery = query || "";

async function loadSearchResults(queryValue, page = 1) {
  if (!queryValue) {
    const resultsContainer = document.getElementById("topbarSearchResults");
    if (resultsContainer) {
      resultsContainer.classList.add("hidden");
      resultsContainer.innerHTML = "";
    }
    return;
  }

  try {
    const searchData = await fetchSeries(queryValue, page);
    renderSeriesResults(searchData);
    currentQuery = queryValue;
    currentPage = page;
  } catch (error) {
    console.error(error);
    showSearchError("Something went wrong. Please try again.");
  }
}

if (query) {
  loadSearchResults(query, currentPage);
}

document.addEventListener("click", async function (e) {
  const target = e.target;

  if (target.classList.contains("pagination-btn")) {
    const page = Number(target.dataset.page) || 1;
    if (currentQuery) {
      e.preventDefault();
      loadSearchResults(currentQuery, page);
    }
    return;
  }

  if (!target.classList.contains("add-watchlist-btn")) {
    return;
  }

  e.preventDefault();
  e.stopPropagation();

  const button = target;
  const seriesId = button.dataset.seriesId;
  const isAdded = button.textContent.trim() === "Added";

  const formData = new FormData();
  const csrfToken = document.getElementById("global-csrf-token").value;
  formData.append("csrf_token", csrfToken);
  formData.append("tmdb_id", seriesId);

  const url = isAdded ? "/watchlist/remove" : "/watchlist/add";

  try {
    const response = await fetch(url, {
      method: "POST",
      body: formData,
      credentials: "include"
    });

    if (!response.ok) {
      alert("Could not update watchlist.");
      return;
    }

    if (isAdded) {
      button.textContent = "Add to Watchlist";
      removeSeriesId(seriesId);
    } else {
      button.textContent = "Added";
      saveSeriesId(seriesId);
    }
  } catch (error) {
    console.error(error);
    alert("Something went wrong.");
  }
});

function updateWatchlistButtonsOnPage() {
  document.querySelectorAll(".add-watchlist-btn").forEach(button => {
    const seriesId = button.dataset.seriesId;

    if (isSeriesSaved(String(seriesId))) {
      button.textContent = "Added";
    } else {
      button.textContent = "Add to Watchlist";
    }
  });
}

function hideSearchResults() {
  const resultsContainer = document.getElementById("topbarSearchResults");
  const searchInput = document.getElementById("topbarSearchInput");

  if (resultsContainer) {
    resultsContainer.classList.add("hidden");
    resultsContainer.innerHTML = "";
  }

  if (searchInput) {
    searchInput.value = "";
  }

  currentQuery = "";
  currentPage = 1;
}

const clearSearchButton = document.getElementById("topbarSearchClear");
if (clearSearchButton) {
  clearSearchButton.addEventListener("click", hideSearchResults);
}

updateWatchlistButtonsOnPage();