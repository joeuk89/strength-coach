"""The Hevy writes of an approved WeekPlan, in ADR 0011's order: folders, exercise templates, one
routine per planned session (its own, else the oldest spare, else a new one), then retires.
Each routine write is read back and mapped `active`, or `unverified` and the run stops."""

import datetime
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal, cast

from coach.core.config import Units
from coach.core.errors import Invalid, Refused
from coach.core.hevy_actions import HevyActions, MapStatus, RoutineAction
from coach.core.instant import parse_instant, utc_instant
from coach.core.mirror import (
    ENGINE_FOLDER_TITLES,
    FolderRole,
    MirroredFolder,
    Routine,
    mirrored_routine,
)
from coach.core.routine_projection import retired_routine, routine_diff
from coach.hevy.protocol import HevyClient, Payload, WriteContext
from coach.services.projections import SessionFacts, projection
from coach.store import exercises, mirrors, routine_map
from coach.store.connection import Connection

type Outcome = Literal["verified", "unverified", "unchanged"]
type Action = Literal["create", "update", "retire"]

ROLES: dict[str, FolderRole] = {title: role for role, title in ENGINE_FOLDER_TITLES.items()}


@dataclass(frozen=True)
class RoutineOutcome:
    session_id: str
    routine_id: str
    action: Action
    outcome: Outcome

    def to_json(self) -> dict[str, object]:
        return {
            "session": self.session_id,
            "routine": self.routine_id,
            "action": self.action,
            "outcome": self.outcome,
        }


@dataclass(frozen=True)
class Guarded:
    """What the guards read live before any write: each touched routine, and the folder each
    missing role adopts (None: create it)."""

    live: Mapping[str, Routine]
    folders: Mapping[FolderRole, str | None]


def guard(conn: Connection, client: HevyClient, actions: HevyActions) -> Guarded:
    """GET every routine the push would overwrite and refuse the whole push when one moved since
    the import; find the folders to adopt by exact title. Nothing is sent before this passes."""
    client.open_audit()
    stored = {r.hevy_id: r.updated_at for r in mirrors.routines(conn)}
    live: dict[str, Routine] = {}
    for routine_id in actions.touched_routines:
        routine = client.routine(routine_id)
        if utc_instant(parse_instant(routine.updated_at)) != stored.get(routine_id):
            raise Refused(
                "routine_moved",
                f"routine {routine_id} changed in Hevy since the last import; run import and "
                "re-check with plan apply --dry-run",
            )
        live[routine_id] = routine
    return Guarded(live, _folders_to_adopt(client, actions.folders))


def _folders_to_adopt(client: HevyClient, titles: Sequence[str]) -> dict[FolderRole, str | None]:
    if not titles:
        return {}
    found = client.folders()
    adopted: dict[FolderRole, str | None] = {}
    for title in titles:
        matches = [f.id for f in found if f.title == title]
        if len(matches) > 1:
            raise Refused(
                "folder_title_shared",
                f"{len(matches)} Hevy folders are titled {title!r}; rename all but one in the app",
            )
        adopted[ROLES[title]] = matches[0] if matches else None
    return adopted


@dataclass
class Push:
    conn: Connection
    client: HevyClient
    plan: Mapping[str, object]
    sessions: Mapping[str, SessionFacts]
    units: Units
    now: datetime.datetime
    outcomes: list[RoutineOutcome] = field(default_factory=list[RoutineOutcome])
    writes: int = 0
    read_backs: int = 0

    @property
    def audit_lines(self) -> int:
        """Two lines per write, one per read-back (ADR 0011, "Write audit")."""
        return 2 * self.writes + self.read_backs

    @property
    def at(self) -> str:
        return utc_instant(self.now)

    def run(self, actions: HevyActions, guarded: Guarded) -> None:
        for role, adopted in guarded.folders.items():
            self._folder(role, adopted)
        for template in actions.templates:
            self._template(template.exercise_id)
        linked = {row.session_id: row.status for row in routine_map.rows(self.conn)}
        for action in actions.updates:
            routine = guarded.live.get(cast(str, action.routine_id))
            unverified = linked[action.session_id] == "unverified"
            self._update(action, self._body(action.session_id), routine, unverified=unverified)
        for action in actions.creates:
            self._create(action, self._body(action.session_id))
        for action in actions.retires:
            self._retire(action, guarded.live[cast(str, action.routine_id)])

    def _folder(self, role: FolderRole, adopted: str | None) -> None:
        title = ENGINE_FOLDER_TITLES[role]
        if adopted is None:
            created = self.client.create_folder(
                {"routine_folder": {"title": title}}, self._context(None)
            )
            self.writes += 1
            adopted = created.id
        with self.conn:
            mirrors.upsert_folder(self.conn, MirroredFolder(role, adopted, title))

    def _template(self, exercise_id: str) -> None:
        row = exercises.get(self.conn, exercise_id)
        assert row is not None
        body: Payload = {
            "exercise": {
                "title": row["hevy_title"],
                "exercise_type": row["hevy_exercise_type"],
                "equipment_category": row["hevy_equipment"],
                "muscle_group": row["hevy_muscle_group"],
                "other_muscles": [],
            }
        }
        template_id = self.client.create_exercise_template(body, self._context(None))
        self.writes += 1
        with self.conn:
            exercises.update(self.conn, exercise_id, {"hevy_template_id": template_id})

    def _update(
        self, action: RoutineAction, body: Payload, live: Routine | None, *, unverified: bool
    ) -> None:
        routine_id = cast(str, action.routine_id)
        if not unverified and live is not None and not routine_diff(body, live):
            self.outcomes.append(
                RoutineOutcome(action.session_id, routine_id, "update", "unchanged")
            )
            with self.conn:
                self._map(action.session_id, routine_id, "active", verified=True)
            return
        self._put(action.session_id, routine_id, body, "update")

    def _create(self, action: RoutineAction, body: Payload) -> None:
        if action.routine_id is not None:
            self._put(action.session_id, action.routine_id, body, "create")
            return
        created = self.client.create_routine({"routine": body}, self._context(None))
        self.writes += 1
        with self.conn:
            mirrors.upsert_routine(self.conn, mirrored_routine(created), self.at)
            self._map(action.session_id, created.id, "unverified", verified=False)
        self._verify(action.session_id, created.id, body, "create", "active")

    def _retire(self, action: RoutineAction, live: Routine) -> None:
        folder = self._folder_id("retired")
        self._put(action.session_id, live.id, retired_routine(live, folder), "retire", "retired")

    def _put(
        self,
        session_id: str,
        routine_id: str,
        body: Payload,
        action: Action,
        verified_status: MapStatus = "active",
    ) -> None:
        self.client.update_routine(routine_id, {"routine": body}, self._context(routine_id))
        self.writes += 1
        self._verify(session_id, routine_id, body, action, verified_status)

    def _verify(
        self, session_id: str, routine_id: str, body: Payload, action: Action, status: MapStatus
    ) -> None:
        read = self.client.read_back(
            routine_id, self._context(routine_id), lambda r: routine_diff(body, r)
        )
        self.read_backs += 1
        with self.conn:
            mirrors.upsert_routine(self.conn, mirrored_routine(read.routine), self.at)
            self._map(
                session_id,
                routine_id,
                status if read.verified else "unverified",
                verified=read.verified,
            )
        outcome: Outcome = "verified" if read.verified else "unverified"
        self.outcomes.append(RoutineOutcome(session_id, routine_id, action, outcome))
        if not read.verified:
            raise Invalid(
                "verify_failed",
                f"routine {routine_id} read back differently ({', '.join(read.diff)}); the run "
                "stopped and a re-run resumes from it",
                {
                    "week_plan_id": self.plan["id"],
                    "routines": [o.to_json() for o in self.outcomes],
                },
            )

    def _map(self, session_id: str, routine_id: str, status: MapStatus, *, verified: bool) -> None:
        routine_map.record(
            self.conn,
            session_id,
            routine_id,
            status,
            plan_id=str(self.plan["id"]),
            at=self.at,
            verified=verified,
        )

    def _body(self, session_id: str) -> Payload:
        return projection(self.conn, self.plan, session_id, self.sessions[session_id], self.units)

    def _folder_id(self, role: FolderRole) -> str:
        found = {f.role: f.hevy_id for f in mirrors.folders(self.conn)}
        return found[role]

    def _context(self, routine_id: str | None) -> WriteContext:
        return WriteContext(str(self.plan["id"]), str(self.plan["write_plan_hash"]), routine_id)
