
# Write the example events.csv
events_csv = '''timestamp_utc,label,position,event_index,gps_epoch_s,offset_us
2026-03-28T11:23:45.012345Z,Condition_A,A,1,1711625025,12345
2026-03-28T11:23:52.998760Z,Condition_B,B,2,1711625032,998760
2026-03-28T11:24:01.000102Z,Condition_A,A,3,1711625041,102
'''

with open('/tmp/gps_logger/events_example.csv', 'w') as fh:
    fh.write(events_csv)
print("events_example.csv written")
