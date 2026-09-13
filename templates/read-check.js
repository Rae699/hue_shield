@@WINDOW@@
var lastCinema = parseInt(getVariable('hsr_last_cinema_ms'), 10) || 0;
var recentCinema = lastCinema > 0 && Date.now() - lastCinema < 3000;
out.ok = true;
if (inWindow && !recentCinema) {
  // The optional fail-open setting preserves Read on unavailable sensor data.
  out.ready = @@FAIL_OPEN@@;
  try {
    var p = response && response.statusCode >= 200 && response.statusCode < 300 ? JSON.parse(response.body) : null;
    var light = p && Array.isArray(p.data) && p.data[0] && p.data[0].light;
    if (light && light.light_level_valid === true && typeof light.light_level === 'number' && Number.isFinite(light.light_level)) {
      out.ready = light.light_level <= @@THRESHOLD@@;
    }
  } catch (error) { /* Keep the configured unavailable-sensor decision. */ }
}
