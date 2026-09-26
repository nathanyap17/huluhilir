/**
 * Wraps app.json so ONE build setting can vary per EAS profile without
 * forking the config: Android cleartext (plain http://) traffic.
 *
 * A release APK blocks http:// by default (Android 9+). The `local` EAS
 * profile (eas.json) bakes in a laptop LAN address like http://192.168.x.x:8000,
 * which is plain http -- so that profile sets ALLOW_CLEARTEXT=1. The `cloud`
 * and `production` profiles talk to Cloud Run over https and must NOT allow
 * cleartext, so they never set it.
 */
module.exports = ({ config }) => {
  const plugins = [...(config.plugins ?? [])];
  if (process.env.ALLOW_CLEARTEXT === "1") {
    plugins.push(["expo-build-properties", { android: { usesCleartextTraffic: true } }]);
  }

  // Google Maps SDK for Android (live walk map, 2026-09-27). The key comes
  // from the environment at build time -- set by release-apk.sh from the
  // gitignored frontend-rn/maps-api.key -- and is never committed. It is
  // restricted in Google Cloud to this package + signing certificate. With
  // no key, the native map stays off (it crashes without one) and the walk
  // falls back to the tile map / readout.
  const mapsKey = process.env.GOOGLE_MAPS_ANDROID_API_KEY;
  const android = mapsKey
    ? { ...config.android, config: { ...(config.android?.config ?? {}), googleMaps: { apiKey: mapsKey } } }
    : config.android;

  return { ...config, plugins, android };
};
