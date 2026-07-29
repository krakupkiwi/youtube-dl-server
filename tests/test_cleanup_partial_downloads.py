import os

from ydl_server.ydlhandler import cleanup_partial_downloads


def test_removes_part_file_for_destination_line(tmp_path):
    dest = tmp_path / "My Video [abc123].mp4"
    part = tmp_path / "My Video [abc123].mp4.part"
    part.write_bytes(b"partial data")

    log = f"[download] Destination: {dest}\n[download]  42.0% of 10.00MiB\n"
    cleanup_partial_downloads(log)

    assert not part.exists()


def test_never_removes_the_final_output_itself(tmp_path):
    dest = tmp_path / "My Video [abc123].mp4"
    dest.write_bytes(b"a fully downloaded file from an earlier segment")

    log = f"[download] Destination: {dest}\n[download] 100% of 10.00MiB\n"
    cleanup_partial_downloads(log)

    assert dest.exists()


def test_no_destination_line_is_a_noop(tmp_path):
    cleanup_partial_downloads("some unrelated log text\n")  # should not raise


def test_missing_part_file_is_a_noop(tmp_path):
    dest = tmp_path / "no [part].mp4"
    log = f"[download] Destination: {dest}\n"
    cleanup_partial_downloads(log)  # .part never existed - should not raise


def test_handles_multiple_destination_lines(tmp_path):
    dest1 = tmp_path / "Part 1 [aaa].mp4"
    dest2 = tmp_path / "Part 2 [bbb].mp4"
    part1 = tmp_path / "Part 1 [aaa].mp4.part"
    part2 = tmp_path / "Part 2 [bbb].mp4.part"
    part1.write_bytes(b"x")
    part2.write_bytes(b"y")

    log = (
        f"[download] Destination: {dest1}\n"
        "[download] 100% of 1.00MiB\n"
        f"[download] Destination: {dest2}\n"
        "[download]  10.0% of 2.00MiB\n"
    )
    cleanup_partial_downloads(log)

    assert not part1.exists()
    assert not part2.exists()
