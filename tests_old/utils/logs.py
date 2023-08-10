def find_log_message(caplog, msg):
    return next((log for log in caplog.records if msg in log.msg['msg']), None)
