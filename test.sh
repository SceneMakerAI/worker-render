#!/bin/bash

curl -X POST http://127.0.0.1:19700/render/sports/baseball \
  -H 'Content-Type: application/json' \
  -d '{"v_id":200, "c_id":1, "file_name":"200.mp4", "sync_yn":true, "bumper_yn":true,
       "innings":{"1_top":[{"start_sec":716,"end_sec":723},{"start_sec":843,"end_sec":851}],
                  "2_top":[{"start_sec":1155,"end_sec":1181}]}}'
