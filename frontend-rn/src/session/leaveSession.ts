import { router } from "expo-router";
import { queryClient } from "../api/queryClient";
import { useSessionStore } from "../store/sessionStore";

/**
 * Detach this phone from its farm and return to the welcome choices
 * (Try demo / Set up my farm / Restore). Only this phone's session is
 * cleared -- nothing is deleted on the server. Shared by "Start over"
 * (unfinished setup) and "Leave the demo farm".
 */
export function leaveToWelcome() {
  useSessionStore.getState().clear();
  queryClient.clear();
  router.replace("/(setup)/welcome");
}
