"""GitHub operation tests for Tiferet child-issue creation and linking.

These tests focus on the integration logic around ordered child issue creation,
parent/sub-issue attachment, and dependency wiring. They exist because the
workflow can appear to succeed locally while GitHub rejects or drops a link.
"""

from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from trigger_workflow_creative_writer.config import TIFERET_AUTO_ISSUE_PREFIX
from trigger_workflow_creative_writer.github_ops import (
    add_blocked_by_dependency,
    add_sub_issue_relationship,
    create_child_issues,
    edit_issue_labels,
    normalize_tiferet_child_title,
    parse_repo,
    remove_issue_label,
    tag_issue_needs_human,
    advance_issue_label,
    verify_parent_sub_issue_ids,
)


class GitHubOpsTests(unittest.TestCase):
    """Exercise GitHub-side orchestration behavior at the command boundary.

    The assertions here are primarily about avoiding operational regressions:
    wrong title normalization, wrong API field types, missed dependency edges,
    or false-positive success when GitHub did not attach the created child
    issues to the parent.
    """

    def test_normalize_tiferet_child_title_adds_prefix_once(self) -> None:
        self.assertEqual(
            normalize_tiferet_child_title("Implement Something"),
            f"{TIFERET_AUTO_ISSUE_PREFIX}Implement Something",
        )
        self.assertEqual(
            normalize_tiferet_child_title(f"{TIFERET_AUTO_ISSUE_PREFIX}Implement Something"),
            f"{TIFERET_AUTO_ISSUE_PREFIX}Implement Something",
        )

    @patch("trigger_workflow_creative_writer.github_ops.time.sleep")
    @patch("trigger_workflow_creative_writer.github_ops.fetch_parent_sub_issue_ids")
    def test_verify_parent_sub_issue_ids_retries_until_links_appear(
        self,
        fetch_parent_sub_issue_ids_mock,
        sleep_mock,
    ) -> None:
        # GitHub can lag before the sub-issue relationship becomes visible.
        # This simulates eventual consistency and ensures the verifier retries
        # before declaring the attachment missing.
        fetch_parent_sub_issue_ids_mock.side_effect = [
            set(),
            {1001},
            {1001, 1002},
        ]

        missing = verify_parent_sub_issue_ids(
            "owner/repo",
            77,
            [1001, 1002],
            attempts=3,
            delay_seconds=0.01,
        )

        self.assertEqual(missing, [])
        self.assertEqual(fetch_parent_sub_issue_ids_mock.call_count, 3)
        self.assertEqual(sleep_mock.call_count, 2)

    @patch("trigger_workflow_creative_writer.github_ops.time.sleep")
    @patch("trigger_workflow_creative_writer.github_ops.fetch_parent_sub_issue_ids", return_value=set())
    def test_verify_parent_sub_issue_ids_returns_missing_after_retry_budget_exhausted(
        self,
        fetch_parent_sub_issue_ids_mock,
        sleep_mock,
    ) -> None:
        missing = verify_parent_sub_issue_ids(
            "owner/repo",
            77,
            [1001, 1002],
            attempts=3,
            delay_seconds=0.01,
        )

        self.assertEqual(missing, [1001, 1002])
        self.assertEqual(fetch_parent_sub_issue_ids_mock.call_count, 3)
        self.assertEqual(sleep_mock.call_count, 2)

    def test_parse_repo_rejects_invalid_identifier(self) -> None:
        with self.assertRaises(SystemExit) as exc:
            parse_repo("owner")

        self.assertIn("Expected 'owner/repo'", str(exc.exception))

    @patch("trigger_workflow_creative_writer.github_ops.run_gh")
    def test_add_sub_issue_relationship_uses_typed_field_submission(self, run_gh_mock) -> None:
        run_gh_mock.return_value = subprocess.CompletedProcess(args=["gh"], returncode=0, stdout="", stderr="")

        add_sub_issue_relationship("owner/repo", 77, 1001)

        self.assertEqual(
            run_gh_mock.call_args.args[0],
            [
                "api",
                "repos/owner/repo/issues/77/sub_issues",
                "--method",
                "POST",
                "-F",
                "sub_issue_id=1001",
            ],
        )

    @patch("trigger_workflow_creative_writer.github_ops.run_gh")
    def test_add_blocked_by_dependency_uses_typed_field_submission(self, run_gh_mock) -> None:
        run_gh_mock.return_value = subprocess.CompletedProcess(args=["gh"], returncode=0, stdout="", stderr="")

        add_blocked_by_dependency("owner/repo", 102, 1001)

        self.assertEqual(
            run_gh_mock.call_args.args[0],
            [
                "api",
                "repos/owner/repo/issues/102/dependencies/blocked_by",
                "--method",
                "POST",
                "-F",
                "issue_id=1001",
            ],
        )

    @patch("trigger_workflow_creative_writer.github_ops.run_gh")
    def test_edit_issue_labels_builds_combined_add_remove_command(self, run_gh_mock) -> None:
        run_gh_mock.return_value = subprocess.CompletedProcess(args=["gh"], returncode=0, stdout="", stderr="")

        edit_issue_labels("owner/repo", 77, add=["phase:netzach"], remove=["phase:tiferet"])

        self.assertEqual(
            run_gh_mock.call_args.args[0],
            [
                "issue",
                "edit",
                "77",
                "--repo",
                "owner/repo",
                "--remove-label",
                "phase:tiferet",
                "--add-label",
                "phase:netzach",
            ],
        )

    @patch("trigger_workflow_creative_writer.github_ops.edit_issue_labels")
    def test_advance_issue_label_uses_shared_label_editor(self, edit_issue_labels_mock) -> None:
        advance_issue_label("owner/repo", 77, "phase:tiferet")

        edit_issue_labels_mock.assert_called_once_with(
            "owner/repo",
            77,
            add=["phase:netzach"],
            remove=["phase:tiferet"],
        )

    @patch("trigger_workflow_creative_writer.github_ops.edit_issue_labels")
    def test_remove_issue_label_uses_shared_label_editor(self, edit_issue_labels_mock) -> None:
        remove_issue_label("owner/repo", 77, "phase:tiferet")
        edit_issue_labels_mock.assert_called_once_with("owner/repo", 77, remove=["phase:tiferet"])

    @patch("trigger_workflow_creative_writer.github_ops.edit_issue_labels")
    def test_tag_issue_needs_human_uses_shared_label_editor(self, edit_issue_labels_mock) -> None:
        tag_issue_needs_human("owner/repo", 77)
        edit_issue_labels_mock.assert_called_once_with("owner/repo", 77, add=["phase:needsHuman"])

class CommentPaginationTests(unittest.TestCase):
    def test_fetch_includes_latest_comment_and_preserves_author_after_first_page(self):
        import json
        from trigger_workflow_creative_writer.github_ops import fetch_issue_data
        def gh(args, **kwargs):
            if args[:2] == ["issue", "view"]:
                payload = {"number": 1, "body": "Intention", "labels": [{"name": "size:season"}],
                           "comments": [{"body": "Bounded stale comment"}]}
            else:
                self.assertEqual(args[:2], ["api", "repos/owner/repo/issues/1/comments"])
                self.assertIn("--paginate", args)
                self.assertIn("--slurp", args)
                payload = [[{"id": 1, "body": "Old cycle", "user": {"login": "robot", "type": "Bot"}, "created_at": "2026-01-01T00:00:00Z"}],
                           [{"id": 101, "body": "Current cycle reply", "user": {"login": "partner", "type": "User"}, "created_at": "2026-01-02T00:00:00Z"}]]
            return subprocess.CompletedProcess(args, 0, json.dumps(payload), "")
        with patch("trigger_workflow_creative_writer.github_ops.run_gh", side_effect=gh):
            issue = fetch_issue_data("owner/repo", 1)
        self.assertEqual([c["body"] for c in issue["comments"]], ["Old cycle", "Current cycle reply"])
        self.assertEqual(issue["comments"][1]["author"], {"login": "partner", "type": "User"})
        self.assertEqual(issue["comments"][1]["createdAt"], "2026-01-02T00:00:00Z")
        self.assertEqual(issue["labels"], [{"name": "size:season"}])


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.issues = []
        self.comments = []
        self.attached = set()
        self.dependencies = {}
        self.fail_attachment = False
        self.fail_discovery = False
        self.attachment_calls = 0
        self.dependency_calls = 0
        self.patcher = patch("trigger_workflow_creative_writer.github_ops.run_gh", side_effect=self.gh)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def gh(self, args, **kwargs):
        import json
        result = None
        if args[:2] == ["issue", "comment"]:
            self.comments.append({"body": args[args.index("--body") + 1]})
            result = {}
        elif args[:2] == ["issue", "view"]:
            result = {"comments": self.comments}
        elif args[0] == "api":
            path = args[1]
            post = "POST" in args
            if path.endswith("/comments"):
                result = self.comments
            elif path.endswith("sub_issues"):
                if post:
                    self.attachment_calls += 1
                    if self.fail_attachment:
                        return subprocess.CompletedProcess(args, 1, "", "attachment unavailable")
                    self.attached.add(int(args[-1].split("=")[1]))
                    result = {}
                else:
                    result = [{"id": value} for value in self.attached]
            elif path.endswith("blocked_by"):
                number = int(path.split("/")[4])
                if post:
                    self.dependency_calls += 1
                    self.dependencies.setdefault(number, set()).add(int(args[-1].split("=")[1]))
                    result = {}
                else:
                    result = [{"id": value} for value in self.dependencies.get(number, set())]
            elif post:
                fields = dict(arg.split("=", 1) for arg in args if "=" in arg and not arg.startswith("labels[]="))
                number = 101 + len(self.issues)
                result = {"number": number, "id": number + 900, "html_url": f"https://example.test/{number}",
                          "title": fields["title"], "body": fields["body"],
                          "labels": [arg.split("=", 1)[1] for arg in args if arg.startswith("labels[]=")]}
                self.issues.append(result)
            else:
                self.assertIn("state=all", path)
                self.assertIn("--paginate", args)
                if self.fail_discovery:
                    return subprocess.CompletedProcess(args, 1, "", "query unavailable")
                result = self.issues
            if "--slurp" in args:
                result = [result]
        else:
            raise AssertionError(args)
        return subprocess.CompletedProcess(args, 0, json.dumps(result), "")

    def assignments(self):
        return [
            {"title": "Confrontation", "body": "A scene", "scope": "scene", "readiness": "ready", "delivery_key": "77-cycle1-scene1"},
            {"title": "Season", "body": "Quoted [SMALL] and scene do not imply readiness", "scope": "episode", "readiness": "develop", "delivery_key": "77-cycle1-season1"},
        ]

    def test_mixed_delivery_routes_by_structured_fields_and_reconciles_retry(self):
        first = create_child_issues("owner/repo", 77, self.assignments())
        second = create_child_issues("owner/repo", 77, self.assignments())
        self.assertEqual(first, second)
        self.assertEqual(len(self.issues), 2)
        self.assertEqual(self.issues[0]["labels"], ["phase:netzach", "size:scene"])
        self.assertEqual(self.issues[1]["labels"], ["phase:keter", "size:episode"])
        self.assertEqual(self.attached, {1001, 1002})
        self.assertEqual(self.dependencies, {77: {1001, 1002}})
        self.assertEqual(self.attachment_calls, 2)
        self.assertEqual(self.dependency_calls, 2)
        self.assertEqual(len(self.comments), 2)
        self.assertIn("101", self.comments[0]["body"])

    def test_interrupted_attachment_recovers_existing_issue(self):
        self.fail_attachment = True
        with self.assertRaises(SystemExit):
            create_child_issues("owner/repo", 77, self.assignments()[:1])
        self.assertEqual(len(self.issues), 1)
        self.fail_attachment = False
        create_child_issues("owner/repo", 77, self.assignments()[:1])
        self.assertEqual(len(self.issues), 1)
        self.assertEqual(self.attached, {1001})

    def test_rejects_legacy_and_invalid_assignments_before_creation(self):
        for changes in ({"scope": "season"}, {"scope": "beat"}, {"scope": "episode", "readiness": "ready"}, {"delivery_key": ""}):
            item = {**self.assignments()[0], **changes}
            with self.assertRaises(SystemExit):
                create_child_issues("owner/repo", 77, [item])
        with self.assertRaises(SystemExit):
            create_child_issues("owner/repo", 77, [{"title": "Legacy", "body": "[SMALL]"}])
        self.assertEqual(self.issues, [])

    def test_unfinished_scene_returns_to_keter(self):
        item = {**self.assignments()[0], "readiness": "develop"}
        create_child_issues("owner/repo", 77, [item])
        self.assertEqual(self.issues[0]["labels"], ["phase:keter", "size:scene"])

    def test_conflicting_or_duplicate_markers_fail_closed(self):
        create_child_issues("owner/repo", 77, self.assignments()[:1])
        original = self.issues[0]["body"]
        self.issues[0]["body"] += "changed"
        with self.assertRaises(SystemExit):
            create_child_issues("owner/repo", 77, self.assignments()[:1])
        self.issues[0]["body"] = original
        self.issues.append(dict(self.issues[0], number=999))
        with self.assertRaises(SystemExit):
            create_child_issues("owner/repo", 77, self.assignments()[:1])

    def test_discovery_failure_prevents_creation(self):
        self.fail_discovery = True
        with self.assertRaises(SystemExit):
            create_child_issues("owner/repo", 77, self.assignments())
        self.assertEqual(self.issues, [])

    def test_missing_attachment_is_not_reported_as_success(self):
        with patch("trigger_workflow_creative_writer.github_ops.verify_parent_sub_issue_ids", return_value=[1001]):
            with self.assertRaisesRegex(SystemExit, "Missing sub-issue links: #101"):
                create_child_issues("owner/repo", 77, self.assignments()[:1])

    def test_later_conflict_prevents_earlier_new_creation(self):
        create_child_issues("owner/repo", 77, self.assignments()[1:])
        self.issues[0]["title"] += "changed"
        with self.assertRaises(SystemExit):
            create_child_issues("owner/repo", 77, self.assignments())
        self.assertEqual(len(self.issues), 1)

    def test_paginated_discovery_includes_later_pages(self):
        from trigger_workflow_creative_writer.github_ops import fetch_paginated_items
        import json
        pages = [[{"number": 1}], [{"number": 2}]]
        with patch("trigger_workflow_creative_writer.github_ops.run_gh", return_value=subprocess.CompletedProcess([], 0, json.dumps(pages), "")):
            self.assertEqual(fetch_paginated_items("owner/repo", "issues?state=all&per_page=100"), [{"number": 1}, {"number": 2}])

    def test_malformed_discovery_fails_closed(self):
        from trigger_workflow_creative_writer.github_ops import fetch_paginated_items
        with patch("trigger_workflow_creative_writer.github_ops.run_gh", return_value=subprocess.CompletedProcess([], 0, '[{}]', "")):
            with self.assertRaises(SystemExit):
                fetch_paginated_items("owner/repo", "issues?state=all&per_page=100")

    def test_deleted_recorded_child_is_not_recreated(self):
        create_child_issues("owner/repo", 77, self.assignments()[:1])
        self.issues.clear()
        with self.assertRaisesRegex(SystemExit, "reconcil"):
            create_child_issues("owner/repo", 77, self.assignments())
        self.assertEqual(self.issues, [])

    def test_conflicting_recorded_identity_stops_before_new_children(self):
        create_child_issues("owner/repo", 77, self.assignments()[1:])
        self.comments[0]["body"] = self.comments[0]["body"].replace('"id":1001', '"id":9999')
        with self.assertRaisesRegex(SystemExit, "reconcil"):
            create_child_issues("owner/repo", 77, self.assignments())
        self.assertEqual(len(self.issues), 1)

    def test_delivery_marker_without_record_requires_reconciliation(self):
        self.comments.append({"body": "<!-- creative-child-delivered:77-cycle1-scene1 -->"})
        with self.assertRaisesRegex(SystemExit, "reconcil"):
            create_child_issues("owner/repo", 77, self.assignments())
        self.assertEqual(self.issues, [])

    def test_conflicting_duplicate_records_require_reconciliation(self):
        create_child_issues("owner/repo", 77, self.assignments()[:1])
        self.comments.append({"body": self.comments[0]["body"].replace('"number":101', '"number":999')})
        with self.assertRaisesRegex(SystemExit, "reconcil"):
            create_child_issues("owner/repo", 77, self.assignments())
        self.assertEqual(len(self.issues), 1)


class CompletionTests(unittest.TestCase):
    def setUp(self):
        import json
        self.issues = {
            1: {"number": 1, "id": 1001, "labels": [{"name": "size:season"}], "state": "open", "body": "Human intention"},
            2: {"number": 2, "id": 1002, "labels": [{"name": "size:episode"}], "state": "open", "body": "Parent issue: #1\n<!-- creative-child:cycle-episode -->"},
            3: {"number": 3, "id": 1003, "labels": [{"name": "size:scene"}], "state": "open", "body": "Parent issue: #2\n<!-- creative-child:cycle-scene -->"},
        }
        from tests.trigger_workflow_creative_writer.test_dramaturgy import established, base
        from trigger_workflow_creative_writer import cycles, validation
        accepted = established()
        result = base('4')
        result['assignments'] = [{'element_id': 'cycle-one:e1', 'outline': 'She chooses her enemy.'}]
        result = validation.validate_result(result, phase='4', cycle_id='cycle-one', scope='season', accepted=accepted)
        assignment = cycles.child_assignments(result, parent_issue=2, accepted=accepted)[0]
        self.issues[3]['body'] += '\n' + assignment['body']
        for item in self.issues.values():
            item["repository_url"] = "https://api.github.com/repos/owner/repo"
        self.parents = {3: 2, 2: 1}
        self.children = {1: [2], 2: [3]}
        self.blockers = {1: [2], 2: [3]}
        self.comments = {
            1: [{"body": '<!-- creative-child-record:{"parent":1,"number":2,"id":1002,"key":"cycle-episode"} -->'}],
            2: [{"body": '<!-- creative-child-record:{"parent":2,"number":3,"id":1003,"key":"cycle-scene"} -->'}],
        }
        self.closed = []
        self.fail_endpoint = None
        self.patcher = patch("trigger_workflow_creative_writer.github_ops.run_gh", side_effect=self.gh)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def gh(self, args, **kwargs):
        import json
        if args[:2] == ["issue", "close"]:
            number = int(args[2])
            self.issues[number]["state"] = "closed"
            self.closed.append(number)
            return subprocess.CompletedProcess(args, 0, "", "")
        self.assertEqual(args[0], "api")
        endpoint = args[1]
        if endpoint == self.fail_endpoint:
            return subprocess.CompletedProcess(args, 1, "", "HTTP 500")
        number = int(endpoint.split("/")[4])
        if endpoint.endswith("/parent"):
            if number not in self.parents:
                return subprocess.CompletedProcess(args, 1, "", "Not Found (HTTP 404)")
            result = self.issues[self.parents[number]]
        elif endpoint.endswith("/sub_issues"):
            result = [self.issues[child] for child in self.children.get(number, [])]
        elif endpoint.endswith("/blocked_by"):
            result = [self.issues[child] for child in self.blockers.get(number, [])]
        elif endpoint.endswith("/comments"):
            result = self.comments.get(number, [])
        else:
            result = self.issues[number]
        if "--slurp" in args:
            result = [result]
        return subprocess.CompletedProcess(args, 0, json.dumps(result), "")

    def complete(self):
        from trigger_workflow_creative_writer import github_ops
        return github_ops.complete_scene_and_roll_up("owner/repo", 3)

    def test_successful_scene_rolls_up_owned_episode_and_season_and_retry(self):
        self.assertEqual(self.complete(), [3, 2, 1])
        self.assertEqual(self.closed, [3, 2, 1])
        self.assertEqual(self.complete(), [])
        self.assertEqual(self.closed, [3, 2, 1])

    def test_open_sibling_prevents_parent_completion(self):
        self.issues[4] = dict(self.issues[3], number=4, id=1004)
        self.children[2].append(4)
        self.blockers[2].append(4)
        self.complete()
        self.assertEqual(self.closed, [3])

    def test_open_external_dependency_prevents_parent_completion(self):
        self.issues[4] = dict(self.issues[3], number=4, id=1004)
        self.blockers[2].append(4)
        self.complete()
        self.assertEqual(self.closed, [3])

    def test_active_parent_or_human_parent_without_records_is_preserved(self):
        for change in ("active", "unowned", "missing_dependency", "missing_marker"):
            with self.subTest(change=change):
                self.setUp()
                if change == "active":
                    self.issues[2]["labels"].append({"name": "phase:keter"})
                elif change == "unowned":
                    self.comments[2] = []
                elif change == "missing_dependency":
                    self.blockers[2] = []
                else:
                    self.issues[3]["body"] = self.issues[3]["body"].replace("<!-- creative-child:cycle-scene -->", "")
                self.complete()
                self.assertEqual(self.closed, [3])

    def test_non_scene_entry_is_rejected_before_closing(self):
        self.issues[3]["labels"] = [{"name": "size:act"}]
        with self.assertRaises(SystemExit):
            self.complete()
        self.assertEqual(self.closed, [])

    def test_parent_lookup_failure_does_not_close_parent(self):
        self.fail_endpoint = "repos/owner/repo/issues/3/parent"
        with self.assertRaises(SystemExit):
            self.complete()
        self.assertEqual(self.closed, [3])

    def test_parent_cycle_stops_without_repeated_closing(self):
        self.parents[1] = 2
        with self.assertRaisesRegex(SystemExit, "cycle"):
            self.complete()
        self.assertEqual(self.closed, [3, 2, 1])

    def test_scene_sized_decomposition_parent_can_complete(self):
        self.issues[2]["labels"] = [{"name": "size:scene"}]
        self.complete()
        self.assertEqual(self.closed, [3, 2, 1])

    def test_cross_repository_parent_is_not_closed(self):
        self.issues[2]["repository_url"] = "https://api.github.com/repos/other/repo"
        with self.assertRaisesRegex(SystemExit, "Cross-repository"):
            self.complete()
        self.assertEqual(self.closed, [3])

    def test_removed_recorded_child_prevents_early_parent_completion(self):
        self.comments[2].append({"body": '<!-- creative-child-record:{"parent":2,"number":9,"id":1009,"key":"removed"} -->'})
        self.complete()
        self.assertEqual(self.closed, [3])

    def test_cancelled_child_and_blocker_prevent_parent_completion(self):
        for relationship in (self.children, self.blockers):
            self.issues[4] = dict(self.issues[3], number=4, id=1004, state="closed", state_reason="not_planned")
            relationship[2].append(4)
            self.complete()
            self.assertEqual(self.closed, [3])
            relationship[2].remove(4)

    def test_leaf_open_or_cancelled_work_prevents_scene_completion(self):
        for state, reason in (("open", None), ("closed", "not_planned")):
            for relationship in (self.children, self.blockers):
                self.issues[4] = dict(self.issues[3], number=4, id=1004, state=state, state_reason=reason)
                relationship[3] = [4]
                with self.assertRaisesRegex(SystemExit, "unfinished|cancelled"):
                    self.complete()
                self.assertEqual(self.closed, [])
                relationship.pop(3)

    def test_legacy_scene_cannot_complete_from_manual_phase_label(self):
        self.issues[3]["body"] = "Legacy [SMALL] prose"
        with self.assertRaisesRegex(SystemExit, "Keter"):
            self.complete()
        self.assertEqual(self.closed, [])

    def test_cancelled_scene_cannot_trigger_rollup(self):
        self.issues[3].update(state="closed", state_reason="not_planned")
        with self.assertRaisesRegex(SystemExit, "cancelled"):
            self.complete()
        self.assertEqual(self.closed, [])

    def test_parent_reconciliation_finishes_after_label_retirement(self):
        from trigger_workflow_creative_writer import github_ops
        self.issues[3].update(state="closed", state_reason="completed")
        self.issues[2]["labels"].append({"name": "phase:tiferet"})
        self.assertEqual(github_ops.reconcile_parent_completion("owner/repo", 2), [])
        self.assertEqual(self.closed, [])
        self.issues[2]["labels"].pop()
        self.assertEqual(github_ops.reconcile_parent_completion("owner/repo", 2), [2, 1])
        self.assertEqual(self.closed, [2, 1])
        self.assertEqual(github_ops.reconcile_parent_completion("owner/repo", 2), [])

    def test_parent_reconciliation_never_closes_leaf(self):
        from trigger_workflow_creative_writer import github_ops
        self.assertEqual(github_ops.reconcile_parent_completion("owner/repo", 3), [])
        self.assertEqual(self.closed, [])
