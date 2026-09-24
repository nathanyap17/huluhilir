import { File, UploadTask, UploadType } from "expo-file-system";
import { apiBase } from "../constants/config";

export interface UploadMediaResult {
  uri: string;
  sha256: string;
  bytes: number;
}

/**
 * Uploads via expo-file-system's native UploadTask (multipart), not raw
 * `fetch` + `FormData` -- confirmed on-device 2026-09-18: RN's own
 * FormData/fetch bridge threw "Unsupported FormDataPart implementation"
 * on this RN version when appending a `{uri, type, name}` object (the
 * long-standing "React Native way" of describing a file part, per RN's
 * own FormData.js docstring -- something changed underneath it). Also
 * removes a second latent bug the fetch path had: it set a bare
 * `Content-Type: multipart/form-data` header with no boundary, which a
 * server can't parse correctly -- fetch/FormData normally generates that
 * boundary itself when Content-Type is left unset.
 *
 * expo-file-system's UploadTask talks to the platform's native upload API
 * directly (no JS-side FormData serialisation at all), so it isn't
 * exposed to either bug. Same backend contract (POST /media,
 * app/routers/media.py's field name "file").
 */
export async function uploadMedia(localUri: string, mimeType: string): Promise<UploadMediaResult> {
  const file = new File(localUri);
  const task = new UploadTask(file, `${apiBase()}/media`, {
    httpMethod: "POST",
    uploadType: UploadType.MULTIPART,
    fieldName: "file",
    mimeType,
  });

  const result = await task.uploadAsync();
  if (result.status < 200 || result.status >= 300) {
    throw new Error(`media upload failed (${result.status}): ${result.body}`);
  }
  return JSON.parse(result.body);
}
