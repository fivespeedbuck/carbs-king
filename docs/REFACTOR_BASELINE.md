# v50.1 architecture refactor baseline

Captured: 2026-07-22

## Required baseline

- Product version: `1.2.1`, build `51`
- Expected tests before the full refactor: `174 passed`, `408 subtests passed`
- `src/main.py`: 4,320 lines
- `src/analytics_views.py`: 1,623 lines
- No commit, tag, APK build, push, or release is allowed during this refactor.

## Existing modified tracked files

- `CHANGELOG.md`
- `android/rest_alarm_plugin/android/src/main/kotlin/com/chenyang/carbs_king/restalarm/RestAlarmReceiver.kt`
- `pyproject.toml`
- `src/achievement_views.py`
- `src/analytics_service.py`
- `src/analytics_views.py`
- `src/main.py`
- `src/rest_notification.py`
- `src/training_experience_service.py`
- `tests/test_achievement_service.py`
- `tests/test_analytics_views.py`
- `tests/test_main_analytics_integration.py`
- `tests/test_rest_notification.py`
- `tests/test_training_experience_service.py`
- `tests/test_ui_contracts.py`

## Existing untracked files to preserve

- `android/rest_alarm_plugin/android/src/main/res/raw/rest_coin.mp3`
- `docs/ARCHITECTURE.md`
- `src/app_defaults.py`
- `src/app_utils.py`
- `src/assets/rest_coin.mp3`
- `src/form_views.py`
- `src/navigation_service.py`
- `src/navigation_views.py`
- `src/profile_views.py`
- `src/storage_service.py`
- `src/today_views.py`
- `src/training_clock_service.py`
- `src/training_views.py`
- `src/ui_components.py`
- `tests/test_navigation_service.py`
- `tests/test_training_clock_service.py`
- `tests/test_view_module_boundaries.py`

This list is evidence of pre-existing v50.1 work. Refactor steps must preserve
these files unless a tested replacement is introduced in the same stage.
