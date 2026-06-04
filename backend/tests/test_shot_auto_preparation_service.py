from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import create_engine

from app.core.db import Base
from app.models.studio import (
    Actor,
    Character,
    CharacterImage,
    CameraAngle,
    CameraMovement,
    CameraShotType,
    Chapter,
    Costume,
    CostumeImage,
    FileItem,
    FileType,
    Project,
    ProjectCostumeLink,
    ProjectPropLink,
    ProjectSceneLink,
    ProjectStyle,
    ProjectVisualStyle,
    Prop,
    PropImage,
    Scene,
    SceneImage,
    Shot,
    ShotCandidateStatus,
    ShotCandidateType,
    ShotCharacterLink,
    ShotDetail,
    ShotDialogLine,
    ShotDialogueCandidateStatus,
    ShotExtractedCandidate,
    ShotExtractedDialogueCandidate,
    ShotStatus,
)
from app.schemas.skills.script_processing import (
    ScriptDivisionResult,
    ShotDivision,
    StudioScriptExtractionDraft,
    StudioShotDraft,
    StudioShotDraftDialogueLine,
)
from app.services.script_processing_worker import DivideTaskExecutor
from app.services.studio.shot_auto_preparation import auto_prepare_chapter_shots_sync


def _build_session() -> tuple[Session, object]:
    engine = create_engine("sqlite:///:memory:", future=True)
    session_local = sessionmaker(engine, class_=Session, expire_on_commit=False)

    import app.models.studio  # noqa: F401

    Base.metadata.create_all(engine)
    return session_local(), engine


def _seed_project_graph(db: Session) -> None:
    project = Project(
        id="project-1",
        name="测试项目",
        style=ProjectStyle.guoman,
        visual_style=ProjectVisualStyle.anime,
    )
    chapter = Chapter(id="chapter-1", project_id=project.id, index=1, title="第一章")
    extracted_at = datetime.now(timezone.utc)
    shots = [
        Shot(id="shot-1", chapter_id=chapter.id, index=1, title="镜头一", script_excerpt="室内交谈", last_extracted_at=extracted_at),
        Shot(id="shot-2", chapter_id=chapter.id, index=2, title="镜头二", script_excerpt="道具特写", last_extracted_at=extracted_at),
        Shot(id="shot-3", chapter_id=chapter.id, index=3, title="镜头三", script_excerpt="模糊匹配", last_extracted_at=extracted_at),
        Shot(id="shot-4", chapter_id=chapter.id, index=4, title="镜头四", script_excerpt="无图资产", last_extracted_at=extracted_at),
    ]
    details = [
        ShotDetail(
            id="shot-1",
            camera_shot=CameraShotType.ms,
            angle=CameraAngle.eye_level,
            movement=CameraMovement.static,
            duration=4,
        ),
        ShotDetail(
            id="shot-2",
            camera_shot=CameraShotType.ms,
            angle=CameraAngle.eye_level,
            movement=CameraMovement.static,
            duration=4,
        ),
        ShotDetail(
            id="shot-3",
            camera_shot=CameraShotType.ms,
            angle=CameraAngle.eye_level,
            movement=CameraMovement.static,
            duration=4,
        ),
        ShotDetail(
            id="shot-4",
            camera_shot=CameraShotType.ms,
            angle=CameraAngle.eye_level,
            movement=CameraMovement.static,
            duration=4,
        ),
    ]
    files = [
        FileItem(id="file-scene", type=FileType.image, name="场景图", storage_key="files/scene.png"),
        FileItem(id="file-character", type=FileType.image, name="角色图", storage_key="files/character.png"),
        FileItem(id="file-prop", type=FileType.image, name="道具图", storage_key="files/prop.png"),
        FileItem(id="file-costume", type=FileType.image, name="服装图", storage_key="files/costume.png"),
    ]
    actor = Actor(
        id="actor-1",
        name="小明演员",
        description="",
        style=ProjectStyle.guoman,
        visual_style=ProjectVisualStyle.anime,
    )
    character = Character(
        id="character-1",
        project_id=project.id,
        name="小明",
        description="",
        style=ProjectStyle.guoman,
        visual_style=ProjectVisualStyle.anime,
        actor_id=actor.id,
    )
    scene = Scene(
        id="scene-1",
        name="控制室",
        description="",
        style=ProjectStyle.guoman,
        visual_style=ProjectVisualStyle.anime,
    )
    fuzzy_prop = Prop(
        id="prop-1",
        name="能量水晶",
        description="",
        style=ProjectStyle.guoman,
        visual_style=ProjectVisualStyle.anime,
    )
    ambiguous_prop = Prop(
        id="prop-ambiguous",
        name="能量水晶碎片",
        description="",
        style=ProjectStyle.guoman,
        visual_style=ProjectVisualStyle.anime,
    )
    costume = Costume(
        id="costume-1",
        name="作战服",
        description="",
        style=ProjectStyle.guoman,
        visual_style=ProjectVisualStyle.anime,
    )
    no_image_scene = Scene(
        id="scene-no-image",
        name="仓库",
        description="",
        style=ProjectStyle.guoman,
        visual_style=ProjectVisualStyle.anime,
    )
    images = [
        CharacterImage(character_id=character.id, file_id="file-character", is_primary=True),
        SceneImage(scene_id=scene.id, file_id="file-scene"),
        PropImage(prop_id=fuzzy_prop.id, file_id="file-prop"),
        CostumeImage(costume_id=costume.id, file_id="file-costume"),
    ]
    db.add_all(
        [
            project,
            chapter,
            *shots,
            *details,
            *files,
            actor,
            character,
            scene,
            fuzzy_prop,
            ambiguous_prop,
            costume,
            no_image_scene,
            *images,
        ]
    )
    db.flush()


def _seed_project_and_assets(db: Session) -> None:
    project = Project(
        id="project-1",
        name="测试项目",
        style=ProjectStyle.guoman,
        visual_style=ProjectVisualStyle.anime,
    )
    chapter = Chapter(id="chapter-1", project_id=project.id, index=1, title="第一章")
    file_item = FileItem(id="file-scene", type=FileType.image, name="场景图", storage_key="files/scene.png")
    scene = Scene(
        id="scene-1",
        name="控制室",
        description="",
        style=ProjectStyle.guoman,
        visual_style=ProjectVisualStyle.anime,
    )
    scene_image = SceneImage(scene_id=scene.id, file_id=file_item.id)
    db.add_all([project, chapter, file_item, scene, scene_image])
    db.flush()


def _division_result() -> ScriptDivisionResult:
    return ScriptDivisionResult(
        shots=[
            ShotDivision(
                index=1,
                start_line=1,
                end_line=2,
                script_excerpt="小明走进控制室，说准备开始。",
                shot_name="进入控制室",
            )
        ],
        total_shots=1,
        notes="test",
    )


def test_auto_prepare_links_assets_with_images_and_accepts_dialogue() -> None:
    db, engine = _build_session()
    try:
        _seed_project_graph(db)
        db.add_all(
            [
                ShotExtractedCandidate(
                    shot_id="shot-1",
                    candidate_type=ShotCandidateType.scene,
                    candidate_name="控制室",
                ),
                ShotExtractedCandidate(
                    shot_id="shot-1",
                    candidate_type=ShotCandidateType.character,
                    candidate_name="小明",
                ),
                ShotExtractedCandidate(
                    shot_id="shot-1",
                    candidate_type=ShotCandidateType.costume,
                    candidate_name="作战服",
                ),
                ShotExtractedDialogueCandidate(
                    shot_id="shot-1",
                    index=1,
                    text="准备开始。",
                    speaker_name="小明",
                ),
            ]
        )
        db.flush()

        summary = auto_prepare_chapter_shots_sync(db, project_id="project-1", chapter_id="chapter-1")

        candidates = db.execute(
            select(ShotExtractedCandidate).where(ShotExtractedCandidate.shot_id == "shot-1")
        ).scalars().all()
        assert all(row.candidate_status == ShotCandidateStatus.linked for row in candidates)
        assert db.scalar(select(ProjectSceneLink).where(ProjectSceneLink.shot_id == "shot-1")) is not None
        assert db.scalar(select(ShotCharacterLink).where(ShotCharacterLink.shot_id == "shot-1")) is not None
        assert db.scalar(select(ProjectCostumeLink).where(ProjectCostumeLink.shot_id == "shot-1")) is not None

        dialogue_candidate = db.scalar(
            select(ShotExtractedDialogueCandidate).where(
                ShotExtractedDialogueCandidate.shot_id == "shot-1"
            )
        )
        assert dialogue_candidate is not None
        assert dialogue_candidate.candidate_status == ShotDialogueCandidateStatus.accepted
        assert dialogue_candidate.linked_dialog_line_id is not None
        assert db.scalar(select(ShotDialogLine).where(ShotDialogLine.shot_detail_id == "shot-1")) is not None
        assert db.get(Shot, "shot-1").status == ShotStatus.ready
        assert summary.linked_asset_count == 3
        assert summary.accepted_dialogue_count == 1
    finally:
        db.close()
        engine.dispose()


def test_auto_prepare_keeps_no_image_assets_pending() -> None:
    db, engine = _build_session()
    try:
        _seed_project_graph(db)
        db.add(
            ShotExtractedCandidate(
                shot_id="shot-4",
                candidate_type=ShotCandidateType.scene,
                candidate_name="仓库",
            )
        )
        db.flush()

        summary = auto_prepare_chapter_shots_sync(db, project_id="project-1", chapter_id="chapter-1")

        candidate = db.scalar(select(ShotExtractedCandidate).where(ShotExtractedCandidate.shot_id == "shot-4"))
        assert candidate is not None
        assert candidate.candidate_status == ShotCandidateStatus.pending
        assert candidate.linked_entity_id is None
        assert db.get(Shot, "shot-4").status == ShotStatus.pending
        assert summary.pending_asset_count == 1
    finally:
        db.close()
        engine.dispose()


def test_auto_prepare_uses_conservative_fuzzy_matching() -> None:
    db, engine = _build_session()
    try:
        _seed_project_graph(db)
        db.add_all(
            [
                ShotExtractedCandidate(
                    shot_id="shot-2",
                    candidate_type=ShotCandidateType.prop,
                    candidate_name="能量水晶",
                ),
                ShotExtractedCandidate(
                    shot_id="shot-3",
                    candidate_type=ShotCandidateType.prop,
                    candidate_name="水晶",
                ),
            ]
        )
        db.flush()

        auto_prepare_chapter_shots_sync(db, project_id="project-1", chapter_id="chapter-1")

        exact_candidate = db.scalar(
            select(ShotExtractedCandidate).where(ShotExtractedCandidate.shot_id == "shot-2")
        )
        ambiguous_candidate = db.scalar(
            select(ShotExtractedCandidate).where(ShotExtractedCandidate.shot_id == "shot-3")
        )
        assert exact_candidate is not None
        assert exact_candidate.candidate_status == ShotCandidateStatus.linked
        assert db.scalar(select(ProjectPropLink).where(ProjectPropLink.shot_id == "shot-2")) is not None
        assert ambiguous_candidate is not None
        assert ambiguous_candidate.candidate_status == ShotCandidateStatus.pending
        assert db.scalar(select(ProjectPropLink).where(ProjectPropLink.shot_id == "shot-3")) is None
    finally:
        db.close()
        engine.dispose()


def test_auto_prepare_dialogue_is_idempotent() -> None:
    db, engine = _build_session()
    try:
        _seed_project_graph(db)
        db.add(
            ShotExtractedDialogueCandidate(
                shot_id="shot-1",
                index=1,
                text="准备开始。",
                speaker_name="小明",
            )
        )
        db.flush()

        auto_prepare_chapter_shots_sync(db, project_id="project-1", chapter_id="chapter-1")
        auto_prepare_chapter_shots_sync(db, project_id="project-1", chapter_id="chapter-1")

        lines = db.execute(select(ShotDialogLine).where(ShotDialogLine.shot_detail_id == "shot-1")).scalars().all()
        assert len(lines) == 1
        candidate = db.scalar(
            select(ShotExtractedDialogueCandidate).where(
                ShotExtractedDialogueCandidate.shot_id == "shot-1"
            )
        )
        assert candidate is not None
        assert candidate.candidate_status == ShotDialogueCandidateStatus.accepted
        assert candidate.linked_dialog_line_id == lines[0].id
    finally:
        db.close()
        engine.dispose()


def test_divide_task_apply_runs_extraction_and_auto_preparation(monkeypatch) -> None:
    db, engine = _build_session()
    try:
        _seed_project_and_assets(db)
        draft = StudioScriptExtractionDraft(
            project_id="project-1",
            chapter_id="chapter-1",
            script_text="小明走进控制室，说准备开始。",
            scenes=[],
            shots=[
                StudioShotDraft(
                    index=1,
                    title="进入控制室",
                    script_excerpt="小明走进控制室，说准备开始。",
                    scene_name="控制室",
                    dialogue_lines=[
                        StudioShotDraftDialogueLine(
                            index=1,
                            text="准备开始。",
                            speaker_name="小明",
                        )
                    ],
                )
            ],
        )

        def _fake_generate_extraction_result(**kwargs):  # noqa: ANN003
            assert kwargs["project_id"] == "project-1"
            assert kwargs["chapter_id"] == "chapter-1"
            return draft, False

        monkeypatch.setattr(
            "app.services.script_processing_worker.generate_extraction_result",
            _fake_generate_extraction_result,
        )

        DivideTaskExecutor().apply_result(
            SimpleNamespace(db=db),
            {"chapter_id": "chapter-1"},
            _division_result(),
        )

        shot = db.scalar(select(Shot).where(Shot.chapter_id == "chapter-1"))
        assert shot is not None
        assert shot.status == ShotStatus.ready
        candidate = db.scalar(select(ShotExtractedCandidate).where(ShotExtractedCandidate.shot_id == shot.id))
        assert candidate is not None
        assert candidate.candidate_status == ShotCandidateStatus.linked
        assert db.scalar(select(ProjectSceneLink).where(ProjectSceneLink.shot_id == shot.id)) is not None
        dialogue_candidate = db.scalar(
            select(ShotExtractedDialogueCandidate).where(ShotExtractedDialogueCandidate.shot_id == shot.id)
        )
        assert dialogue_candidate is not None
        assert dialogue_candidate.candidate_status == ShotDialogueCandidateStatus.accepted
        assert db.scalar(select(ShotDialogLine).where(ShotDialogLine.shot_detail_id == shot.id)) is not None
    finally:
        db.close()
        engine.dispose()
