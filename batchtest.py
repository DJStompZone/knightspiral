import os

def run(i, num_colors = 4, teams="black red green blue", colors="#000000 #CC0000 #00AA00 #0000CC"):
    template = f"poetry run python3 -m knightspiral {i} --teams {teams} --color {colors} --raster ../knightspiral_{num_colors}colors_{i}.png --no-draw"
    os.system(template)

def runbatch(starting=100):
    steps = starting
    for step in range(10):
        run(steps, 4)
        steps *= 10
        print(f"Running next run with {steps} steps")

if __name__ == "__main__":
    runbatch()