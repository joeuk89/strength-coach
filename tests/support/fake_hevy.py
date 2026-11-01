import copy
import datetime
from collections.abc import Iterable
from typing import Any, cast

from coach.core.clock import Clock
from coach.core.errors import Unreachable
from coach.core.mirror import (
    BodyMeasurement,
    ExerciseTemplate,
    Folder,
    Routine,
    Workout,
    WorkoutEvent,
)
from coach.hevy import audit
from coach.hevy.parse import (
    parse_body_measurement_page,
    parse_exercise_template_page,
    parse_folder,
    parse_folder_page,
    parse_routine,
    parse_routine_page,
    parse_workout_events_page,
    parse_workout_page,
)
from coach.hevy.protocol import Payload, ReadBack, RoutineDiff, WriteContext

type Json = dict[str, Any]


class FakeHevy:
    """The in-process `HevyClient` every service test uses (testing.md, "The fake Hevy").

    It holds Hevy-shaped payloads and answers through the real parsers, so it returns the values
    the real client would. Like Hevy, a PUT drops the routine-level note.
    """

    def __init__(
        self,
        clock: Clock,
        *,
        workouts: Iterable[Json] = (),
        events: Iterable[Json] = (),
        routines: Iterable[Json] = (),
        folders: Iterable[Json] = (),
        templates: Iterable[Json] = (),
        measurements: Iterable[Json] = (),
    ) -> None:
        self._clock = clock
        self._workouts = [copy.deepcopy(w) for w in workouts]
        self._events = [copy.deepcopy(e) for e in events]
        self._routines = {str(r["id"]): copy.deepcopy(r) for r in routines}
        self._folders = [copy.deepcopy(f) for f in folders]
        self._templates = [copy.deepcopy(t) for t in templates]
        self._measurements = [copy.deepcopy(m) for m in measurements]
        self._created = 0
        self._fail_next_get = False
        self._differ_next_read_back = False
        self.audit: list[audit.AuditLine] = []

    def move_routine(self, routine_id: str, updated_at: str) -> None:
        self._routines[routine_id]["updated_at"] = updated_at

    def fail_next_get(self) -> None:
        self._fail_next_get = True

    def differ_next_read_back(self) -> None:
        self._differ_next_read_back = True

    def open_audit(self) -> None:
        pass

    def create_routine(self, body: Payload, context: WriteContext) -> Routine:
        sent = _routine_body(body)
        routine_id = self._new_id("routine")
        self._routines[routine_id] = self._stored_routine(routine_id, sent, keep_notes=True)
        return self._write("POST", "/v1/routines", body, context, routine_id)

    def update_routine(self, routine_id: str, body: Payload, context: WriteContext) -> Routine:
        self._require(routine_id)
        sent = _routine_body(body)
        self._routines[routine_id] = self._stored_routine(routine_id, sent, keep_notes=False)
        return self._write("PUT", f"/v1/routines/{routine_id}", body, context, routine_id)

    def create_folder(self, body: Payload, context: WriteContext) -> Folder:
        sent = cast(Json, body["routine_folder"])
        folder: Json = {
            "id": 9000 + len(self._folders),
            "index": len(self._folders),
            "title": sent["title"],
            "updated_at": self._clock.now().isoformat(),
            "created_at": self._clock.now().isoformat(),
        }
        self._folders.append(folder)
        self._audit_write("POST", "/v1/routine_folders", body, context)
        return parse_folder(folder)

    def create_exercise_template(self, body: Payload, context: WriteContext) -> str:
        sent = cast(Json, body["exercise"])
        template_id = self._new_id("template")
        self._templates.append(
            {
                "id": template_id,
                "title": sent["title"],
                "type": sent.get("exercise_type"),
                "primary_muscle_group": sent.get("muscle_group"),
                "secondary_muscle_groups": list(sent.get("other_muscles") or []),
                "equipment": sent.get("equipment_category"),
                "is_custom": True,
            }
        )
        self._audit_write("POST", "/v1/exercise_templates", body, context)
        return template_id

    def workouts(self) -> tuple[Workout, ...]:
        return parse_workout_page(self._page("workouts", self._workouts)).items

    def workout_events(self, since: datetime.datetime) -> tuple[WorkoutEvent, ...]:
        newer = [e for e in self._events if _event_moment(e) > since]
        return parse_workout_events_page(self._page("events", newer)).items

    def routines(self) -> tuple[Routine, ...]:
        return parse_routine_page(self._page("routines", list(self._routines.values()))).items

    def routine(self, routine_id: str) -> Routine:
        self._get()
        self._require(routine_id)
        return parse_routine({"routine": self._routines[routine_id]})

    def read_back(self, routine_id: str, context: WriteContext, diff: RoutineDiff) -> ReadBack:
        routine = self.routine(routine_id)
        if self._differ_next_read_back:
            self._differ_next_read_back = False
            routine = parse_routine({"routine": _differing(self._routines[routine_id])})
        found = diff(routine)
        self.audit.append(audit.verify_line(self._clock.now(), routine_id, context, found))
        return ReadBack(routine=routine, diff=found)

    def folders(self) -> tuple[Folder, ...]:
        return parse_folder_page(self._page("routine_folders", self._folders)).items

    def exercise_templates(self) -> tuple[ExerciseTemplate, ...]:
        return parse_exercise_template_page(self._page("exercise_templates", self._templates)).items

    def body_measurements(self) -> tuple[BodyMeasurement, ...]:
        page = self._page("body_measurements", self._measurements)
        return parse_body_measurement_page(page).items

    def _require(self, routine_id: str) -> None:
        if routine_id not in self._routines:
            raise Unreachable("hevy_unreachable", f"Hevy has no routine {routine_id}")

    def _get(self) -> None:
        if self._fail_next_get:
            self._fail_next_get = False
            raise Unreachable("hevy_unreachable", "could not reach Hevy (a planted failure)")

    def _page(self, key: str, items: list[Json]) -> Json:
        self._get()
        return {"page": 1, "page_count": 1, key: copy.deepcopy(items)}

    def _new_id(self, kind: str) -> str:
        self._created += 1
        return f"fake-{kind}-{self._created:04d}"

    def _stored_routine(self, routine_id: str, sent: Json, *, keep_notes: bool) -> Json:
        titles = {t["id"]: t["title"] for t in self._templates}
        now = self._clock.now().isoformat()
        return {
            "id": routine_id,
            "title": sent["title"],
            "folder_id": sent.get("folder_id"),
            "notes": sent.get("notes") if keep_notes else None,
            "updated_at": now,
            "created_at": self._routines.get(routine_id, {}).get("created_at", now),
            "exercises": [
                {
                    "index": index,
                    "title": titles.get(exercise["exercise_template_id"]),
                    "rest_seconds": exercise.get("rest_seconds"),
                    "notes": exercise.get("notes"),
                    "exercise_template_id": exercise["exercise_template_id"],
                    "superset_id": exercise.get("superset_id"),
                    "sets": [{"index": n, **s} for n, s in enumerate(exercise.get("sets") or [])],
                }
                for index, exercise in enumerate(sent.get("exercises") or [])
            ],
        }

    def _write(
        self, method: str, path: str, body: Payload, context: WriteContext, routine_id: str
    ) -> Routine:
        self._audit_write(method, path, body, context)
        return parse_routine({"routine": self._routines[routine_id]})

    def _audit_write(self, method: str, path: str, body: Payload, context: WriteContext) -> None:
        now = self._clock.now()
        self.audit.append(audit.request_line(now, method, path, body, context))
        self.audit.append(audit.response_line(now, method, path, body, attempts=1, status=200))


def _routine_body(body: Payload) -> Json:
    return copy.deepcopy(cast(Json, body["routine"]))


def _event_moment(event: Json) -> datetime.datetime:
    stamp = event["deleted_at"] if event["type"] == "deleted" else event["workout"]["updated_at"]
    return datetime.datetime.fromisoformat(stamp)


def _differing(routine: Json) -> Json:
    changed = copy.deepcopy(routine)
    sets = [s for e in changed["exercises"] for s in e["sets"]]
    if sets:
        sets[0]["weight_kg"] = (sets[0].get("weight_kg") or 0.0) + 2.5
    else:
        changed["title"] = f"{changed['title']} (edited in the app)"
    return changed
