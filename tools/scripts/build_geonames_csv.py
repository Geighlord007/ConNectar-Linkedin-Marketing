import csv
import os
import sys

"""
通用版：从 GeoNames dump <CC>.txt 生成简化索引 CSV：data/geo/geonames_<cc>.csv

输出列：name, state, country
规则：仅保留 feature class == 'P'（居民点），优先 admin1_code 作为州/省缩写。
用于地点规范化的快速索引构建。

使用方式：
  环境变量：
    GEONAMES_TXT = data/geonames/<CC>/<CC>.txt
    GEONAMES_CSV = data/geo/geonames_<cc>.csv
  或命令行：
    python tools/scripts/build_geonames_csv.py data/geonames/US/US.txt data/geo/geonames_us.csv
"""


def build(input_path: str, output_path: str) -> None:
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    total = 0
    kept = 0
    with open(input_path, 'r', encoding='utf-8', newline='') as fin, \
         open(output_path, 'w', encoding='utf-8', newline='') as fout:
        writer = csv.writer(fout)
        writer.writerow(['name', 'state', 'country'])
        for line in fin:
            total += 1
            line = line.rstrip('\n')
            if not line or line.startswith('#'):
                continue
            parts = line.split('\t')
            if len(parts) < 11:
                continue
            country = parts[8]
            fclass = parts[6]
            if fclass != 'P':
                continue
            name = parts[1].strip()
            state = parts[10].strip().upper() if len(parts) > 10 else ''
            if not name or not state:
                continue
            if len(name) < 2:
                continue
            writer.writerow([name, state, country])
            kept += 1

    print(f"Processed lines: {total}, kept cities: {kept} -> {output_path}")


if __name__ == '__main__':
    if len(sys.argv) >= 3:
        in_path = sys.argv[1]
        out_path = sys.argv[2]
    else:
        in_path = os.environ.get('GEONAMES_TXT', os.path.join('data', 'geonames', 'US', 'US.txt'))
        out_path = os.environ.get('GEONAMES_CSV', os.path.join('data', 'geo', 'geonames_us.csv'))
    build(in_path, out_path)


