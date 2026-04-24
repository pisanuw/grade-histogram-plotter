from flask import Flask, render_template, request
import statistics
import matplotlib
from matplotlib.figure import Figure
import base64
from io import BytesIO
from datetime import datetime
import os

matplotlib.use('Agg')

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(BASE_DIR, 'log.txt')
DEFAULT_CUTOFFS = [50.0, 60.0, 70.0, 80.0, 90.0]
DEFAULT_GRADES = "70\n75\n80\n85\n85\n85\n75\n80\n85\n85\n85\n75\n80\n85\n85\n85\n90\n100"


def get_cutoffs():
  raw_cutoffs = request.form.get('cutoffs', '')
  return parse_cutoffs(raw_cutoffs)


def get_grades():
  raw_grades = request.form.get('grades', '')
  return [x.strip() for x in raw_grades.split('\n') if x.strip() != ""]


def format_cutoff(value):
  value = float(value)
  return str(int(value)) if value.is_integer() else str(value)


def parse_cutoffs(raw_cutoffs):
  buckets = [x.strip() for x in raw_cutoffs.split('\n') if x.strip() != ""]
  if not buckets:
    return DEFAULT_CUTOFFS.copy()

  try:
    parsed = [float(x) for x in buckets]
  except ValueError as exc:
    raise ValueError('Cutoffs must contain only numbers, one per line.') from exc

  if parsed != sorted(parsed):
    raise ValueError('Cutoffs must be in ascending order.')

  if len(set(parsed)) != len(parsed):
    raise ValueError('Cutoffs must not contain duplicates.')

  return parsed


def buckets2labels(cutoffs):
  label = []
  label.append("<" + format_cutoff(cutoffs[0]))
  i = 1
  while i < len(cutoffs):
    lower = format_cutoff(cutoffs[i - 1])
    upper_value = cutoffs[i] - 1 if float(cutoffs[i]).is_integer() else cutoffs[i]
    upper = format_cutoff(upper_value)
    label.append(str(lower) + "-" + str(upper))
    i = i + 1
  label.append(">=" + format_cutoff(cutoffs[-1]))
  label.append("NaN")
  return label


def process_post():
  ip_addr = request.environ.get('REMOTE_ADDR', 'unknown')
  dateTimeObj = datetime.now().isoformat(timespec='seconds')
  with open(LOG_PATH, 'a', encoding='utf-8') as f:
    f.write(dateTimeObj + ": " + ip_addr + "\n")

  cutoffs_text = request.form.get('cutoffs', '').strip()
  grades_text = request.form.get('grades', '').strip()

  try:
    plot_data = plot_png()
  except ValueError as exc:
    return render_template('input-grades.html',
                           default_cutoffs=cutoffs_text or "\n".join(
                             format_cutoff(x) for x in DEFAULT_CUTOFFS),
                           default_grades=grades_text or DEFAULT_GRADES,
                           error_message=str(exc)), 400

  return render_template('result.html', plot_data=plot_data)


@app.route("/", methods=['POST', 'GET'])
def hello_world():
  if request.method == 'GET':
    return render_template('input-grades.html',
                           default_cutoffs="\n".join(
                             format_cutoff(x) for x in DEFAULT_CUTOFFS),
                           default_grades=DEFAULT_GRADES,
                           error_message=None)
  else:
    return process_post()


def plot_png():
  fig = create_bar_plot()
  buf = BytesIO()
  fig.savefig(buf, format="png")
  data = base64.b64encode(buf.getbuffer()).decode("ascii")
  return f"<img src='data:image/png;base64,{data}'/>"


def create_bar_plot():
  fig = Figure()
  axis = fig.add_subplot(1, 1, 1)
  cutoffs = get_cutoffs()
  props = dict(boxstyle='round', facecolor='wheat', alpha=0.5)
  data = get_grades()
  if not data:
    raise ValueError('Enter at least one grade.')
  xs = buckets2labels(cutoffs)
  ys = data_into_buckets(data, cutoffs)
  # if no NaN data get rid of the bucket and the label
  if len(xs) > len(ys):
    xs.pop()
  textstr = get_dist_stats(data, ys)
  axis.text(0.02,
            0.95,
            textstr,
            transform=axis.transAxes,
            fontsize=10,
            verticalalignment='top',
            bbox=props)
  axis.bar(xs, ys)
  axis.set_xlabel("Grades")
  axis.set_ylabel("# of Students")
  # fig.suptitle("Course Number")
  fig.tight_layout()
  return fig


def get_dist_stats(data, distribution):
  intData = [float(x) for x in data if isFloat(x)]
  if not intData:
    return '\n'.join((
      "Total: " + str(len(data)),
      "Mean: n/a",
      "Median: n/a",
      "Stdev: n/a",
      "Min: n/a",
      "Max: n/a",
      "Dist: [" + ", ".join([str(x) for x in distribution]) + "]"))

  stdevA = "0.0"
  if len(intData) > 1:
    stdevA = str(round(statistics.stdev(intData), 1))

  total = sum(distribution)
  if total:
    percentages = "Pct: [" + ", ".join(
      [str(int(round((x / total) * 100, 0))) for x in distribution]) + "]"
  else:
    percentages = "Pct: []"

  textstr = '\n'.join((
    "Total: " + str(len(data)),
    "Mean: " + str(round(statistics.mean(intData), 1)),
    "Median: " + str(round(statistics.median(intData), 1)),
    # "Mode: " + str(round(statistics.mode(intData), 1)),
    "Stdev: " + stdevA,
    "Min: " + str(round(min(intData), 1)),
    "Max: " + str(round(max(intData), 1)),
    "Dist: [" + ", ".join([str(x) for x in distribution]) + "]",
    percentages))
  return textstr


def data_into_buckets(data, cutoffs):
  # buckets = [0, 0, 0, 0, 0, 0, 0]
  buckets = [0] * (len(cutoffs) + 2)
  # ["<50", "50-59", "60-69", "70-79", "80-89", ">=90", "NaN"]
  for grade in data:
    if not isFloat(grade):
      buckets[-1] = buckets[-1] + 1
      continue
    else:
      grade = float(grade)
    i = 0
    inserted = False
    while not inserted and i < len(cutoffs):
      if grade < cutoffs[i]:
        inserted = True
        buckets[i] = buckets[i] + 1
      i = i + 1
    if not inserted:
      buckets[-2] = buckets[-2] + 1
  if buckets[-1] == 0:
    buckets.pop()
  return buckets


def isFloat(s):
  try:
    float(s)
    return True
  except ValueError:
    return False

if __name__ == '__main__':
  port = int(os.environ.get('PORT', 5000))
  app.run(host='0.0.0.0', port=port, debug=True)
