// Static strings only: upstream response text must never enter Leaflet HTML.
export const routingAttribution = (provider?: string): string =>
  provider === 'google'
    ? 'Útvonal: Google Maps'
    : 'Útvonal: <a href="https://project-osrm.org/">OSRM</a> · <a href="https://routing.openstreetmap.de/about.html">FOSSGIS</a> · <a href="https://www.openstreetmap.org/fixthemap">Térkép javítása</a>'
