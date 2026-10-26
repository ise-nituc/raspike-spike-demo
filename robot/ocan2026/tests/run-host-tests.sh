#!/usr/bin/env bash
set -euo pipefail
app_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
test_dir="${app_dir}/tests"
build_dir="$(mktemp -d)"
trap 'rm -rf "${build_dir}"' EXIT
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -pedantic \
    -I"${test_dir}/stubs" -I"${app_dir}" -I"${app_dir}/LineTracer" \
    "${app_dir}/app.c" "${app_dir}/LineTracer/LineTracer.c" \
    "${app_dir}/LineTracer/RobotControl.c" "${test_dir}/test_button_control.c" \
    -o "${build_dir}/test_button_control"
"${build_dir}/test_button_control"
