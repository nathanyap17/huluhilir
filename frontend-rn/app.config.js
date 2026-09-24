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
  return { ...config, plugins };
};
