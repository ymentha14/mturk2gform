#!/bin/bash
# A simple mouse clicker to run automate appscripts jobs generation
# Google drive limits the free account running time to 6min: the scripts
# present in this directory allows you to schedule appscript runs and append
# the results into a single file
tim=1;
iterations=41;
for ((i=1;i<=iterations;i++)); do
  echo "iteration $i"
  xdotool mousemove --sync 231 190 click 1 &&
  sleep "$tim" &&
  xdotool mousemove --sync 281 233 click 1 &&
  sleep "$tim" &&
  xdotool mousemove --sync 765 241 &&
  sleep "$tim" &&
  echo "step 4" &&
  xdotool mousemove --sync 821 610 click 1 &&
  sleep 200
done
