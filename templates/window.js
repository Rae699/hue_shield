var now = new Date();
var minute = now.getHours() * 60 + now.getMinutes();
var startMinute = @@START@@;
var endMinute = @@END@@;
var inWindow = startMinute < endMinute ? minute >= startMinute && minute < endMinute : minute >= startMinute || minute < endMinute;
