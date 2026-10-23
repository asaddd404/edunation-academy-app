import { isAxiosError } from "axios";

/**
 * A sentence a user can act on, for any failed API call.
 *
 * FastAPI refuses a request either with a string `detail` (written for the
 * user, in Russian) or with a list of field errors from validation; anything
 * else -- a 5xx, no response at all -- gets a plain fallback rather than an
 * HTTP status the user has no use for.
 */
export function describeApiError(error: unknown, fallback = "Что-то пошло не так. Попробуйте ещё раз."): string {
  if (!isAxiosError(error)) return fallback;
  if (!error.response) return "Нет связи с сервером. Проверьте интернет и попробуйте ещё раз.";

  const { status, data } = error.response;
  const detail = (data as { detail?: unknown } | undefined)?.detail;
  if (typeof detail === "string" && status < 500) return detail;
  if (Array.isArray(detail) && detail.length) {
    const first = detail[0] as { msg?: string };
    if (first?.msg) return translateValidation(String(first.msg));
  }
  if (status === 413) return "Файл или текст слишком большой.";
  if (status === 429) return "Слишком много запросов. Подождите немного и повторите.";
  if (status >= 500) return "Сервер не смог выполнить запрос. Попробуйте ещё раз чуть позже.";
  return fallback;
}

/** Errors the app already deals with elsewhere and must not toast about:
 * a 401 is the auth interceptor's job (refresh, or back to login), and a
 * request the code cancelled on purpose is not a failure. */
export function isHandledElsewhere(error: unknown): boolean {
  if (!isAxiosError(error)) return false;
  return error.code === "ERR_CANCELED" || error.response?.status === 401;
}

/** FastAPI's own field errors arrive in English; the app's validators
 * already answer in Russian ("Value error, ..." -- the prefix is dropped). */
const PYDANTIC_MESSAGES: [RegExp, (m: RegExpMatchArray) => string][] = [
  [/^String should have at most (\d+) characters?$/, (m) => `Слишком длинное значение: не больше ${m[1]} символов.`],
  [/^String should have at least (\d+) characters?$/, (m) => `Слишком короткое значение: не меньше ${m[1]} символов.`],
  [/^List should have at most (\d+) items?/, (m) => `Слишком много элементов: не больше ${m[1]}.`],
  [/^Field required$/, () => "Заполните обязательное поле."],
  [/^Input should be a valid integer/, () => "Ожидается целое число."],
];

export function translateValidation(message: string): string {
  const text = message.replace(/^Value error, /, "");
  for (const [pattern, render] of PYDANTIC_MESSAGES) {
    const match = text.match(pattern);
    if (match) return render(match);
  }
  return text;
}
