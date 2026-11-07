const API_BASE = "";

async function checkHealth() {
  try {
    const res = await fetch(`${API_BASE}/api/health`);
    const data = await res.json();
    console.log("API health:", data);
  } catch (e) {
    console.error("Backend not reachable:", e);
  }
}

checkHealth();
