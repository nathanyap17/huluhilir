import AsyncStorage from "@react-native-async-storage/async-storage";
import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import type { components } from "../api-types";

type FarmOut = components["schemas"]["FarmOut"];
type UserOut = components["schemas"]["UserOut"];

interface SessionState {
  user: UserOut | null;
  farm: FarmOut | null;
  // True on a phone attached to the shared demo farm: settings that would
  // change it for every other demo device (name, language) stay on-device.
  isDemo: boolean;
  setUser: (user: UserOut) => void;
  setFarm: (farm: FarmOut) => void;
  setIsDemo: (isDemo: boolean) => void;
  clear: () => void;
}

/**
 * Only user_id/farm_id (and a locally cached copy of the farm row) persist
 * on-device. `setup_completed_at` is the hard gate the root layout checks on
 * every cold start (docs/PROJECT_SPEC.md §9.0) -- but PROJECT_SPEC.md itself
 * warns against "trusting a stale local copy" (see GET /farms/{farm_id}'s
 * docstring), so the cached `farm` here is a fast first paint only; the root
 * layout re-fetches from the server before trusting it for the actual gate
 * decision.
 */
export const useSessionStore = create<SessionState>()(
  persist(
    (set) => ({
      user: null,
      farm: null,
      isDemo: false,
      setUser: (user) => set({ user }),
      setFarm: (farm) => set({ farm }),
      setIsDemo: (isDemo) => set({ isDemo }),
      clear: () => set({ user: null, farm: null, isDemo: false }),
    }),
    {
      name: "pepperdex-session",
      storage: createJSONStorage(() => AsyncStorage),
    }
  )
);
