import csv
import os

"""
从 GeoNames dump US.txt 生成简化城市索引 CSV：data/geo/geonames_us.csv

输入（默认）：data/geonames/US/US.txt  (tab 分隔)
Dump列说明（allCountries/US dump统一格式）：
 0 geonameid
 1 name
 2 asciiname
 3 alternatenames
 4 latitude
 5 longitude
 6 feature class
 7 feature code
 8 country code
 9 cc2
10 admin1 code (US: 州缩写，如 RI, MA)
11 admin2 code
12 admin3 code
13 admin4 code
14 population
15 elevation
16 dem
17 timezone
18 modification date

我们只输出：name, state, country 三列，且仅保留 US 且 feature class=="P" 的居民点。
输出重复城市名会保留所有州（上游使用时去重为 city->{ST} 集合）。
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
            if country != 'US':
                continue
            fclass = parts[6]
            if fclass != 'P':  # 仅居民点，提高精度
                continue
            name = parts[1].strip()
            state = parts[10].strip().upper() if len(parts) > 10 else ''
            if not name or not state:
                continue
            # 过滤过短或噪声名
            if len(name) < 2:
                continue
            writer.writerow([name, state, 'US'])
            kept += 1

    print(f"Processed lines: {total}, kept cities: {kept}")


if __name__ == '__main__':
    in_path = os.environ.get('GEONAMES_US_TXT', os.path.join('data', 'geonames', 'US', 'US.txt'))
    out_path = os.environ.get('GEONAMES_US_CSV', os.path.join('data', 'geo', 'geonames_us.csv'))
    build(in_path, out_path)


