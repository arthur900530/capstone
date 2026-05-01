/**
 * Fallback for batch size when `/api/employees/auto_tests_config` is unavailable.
 * Keep in sync with the default in ``backend/config.py`` → ``TEST_SUITE_GENERATION_COUNT``.
 *
 * The live value is read from the backend (same ``config.py`` / env key).
 */
export const TEST_SUITE_GENERATION_COUNT_FALLBACK = 6;

/** Environment variable name on the backend (see ``backend/config.py``). */
export const TEST_SUITE_GENERATION_COUNT_ENV = "TEST_SUITE_GENERATION_COUNT";
