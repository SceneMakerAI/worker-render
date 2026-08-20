#!/bin/bash
# 야구 렌더 — 범퍼 없이 (bumper_yn=false)
# 원본: {VOD_DIR}/201/201.mp4, 결과: {VOD_DIR}/201/result/201_1.mp4

curl -X POST http://127.0.0.1:19700/render/sports/baseball \
  -H 'Content-Type: application/json' \
  -d '{"v_id":201, "c_id":1, "sync_yn":true, "bumper_yn":false,
       "innings":{"1_top":[{"start_sec":714,"end_sec":725,"start_hms":"00:11:54.0","end_hms":"00:12:05.0"}],
                  "1_bot":[{"start_sec":1051,"end_sec":1060,"start_hms":"00:17:31.0","end_hms":"00:17:40.0"},
                           {"start_sec":1342,"end_sec":1354,"start_hms":"00:22:22.0","end_hms":"00:22:34.0"}]}}'
echo
