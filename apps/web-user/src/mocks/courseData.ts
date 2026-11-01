// 조리읍 2026년 4분기 강좌 25개를 시안(courses.html과 상세 페이지)에서 한 번 추출한 개발용 샘플 데이터. 공고 값 그대로이며 점유·대기 같은 가상 값은 넣지 않았다
import type { Schemas } from '@jori/api-client';

type Weekday = Schemas['Weekday'];

export interface CourseSeed {
  id: string;
  name: string;
  categoryId: string;
  instructorName: string | null;
  schedules: { days: Weekday[]; startTime: string; endTime: string; label: string | null }[];
  room: string | null;
  fee: number;
  capacity: number;
}

export const CATEGORY_SEEDS = [
  { categoryId: '1', name: '컴퓨터' },
  { categoryId: '2', name: '어학/교양' },
  { categoryId: '3', name: '생활체육/건강' },
  { categoryId: '4', name: '문화/취미' },
];

export const COURSE_SEEDS: CourseSeed[] = [
  {
    "id": "1",
    "name": "초급컴퓨터",
    "categoryId": "1",
    "instructorName": "추순자",
    "schedules": [
      {
        "days": [
          "TUE",
          "THU"
        ],
        "startTime": "10:00",
        "endTime": "11:30",
        "label": null
      }
    ],
    "room": "문화교실4번",
    "fee": 60000,
    "capacity": 12
  },
  {
    "id": "2",
    "name": "생활영어",
    "categoryId": "2",
    "instructorName": "세이엘리자벧시",
    "schedules": [
      {
        "days": [
          "TUE",
          "THU"
        ],
        "startTime": "11:30",
        "endTime": "13:00",
        "label": null
      }
    ],
    "room": "문화교실1번",
    "fee": 60000,
    "capacity": 25
  },
  {
    "id": "3",
    "name": "라인댄스 A",
    "categoryId": "3",
    "instructorName": "정은경",
    "schedules": [
      {
        "days": [
          "MON",
          "THU"
        ],
        "startTime": "14:00",
        "endTime": "15:30",
        "label": null
      }
    ],
    "room": "문화교실3번",
    "fee": 60000,
    "capacity": 25
  },
  {
    "id": "4",
    "name": "통 기 타",
    "categoryId": "4",
    "instructorName": "안석상",
    "schedules": [
      {
        "days": [
          "MON",
          "TUE"
        ],
        "startTime": "19:00",
        "endTime": "20:30",
        "label": null
      }
    ],
    "room": "문화교실2번",
    "fee": 60000,
    "capacity": 25
  },
  {
    "id": "5",
    "name": "한글문해교실",
    "categoryId": "2",
    "instructorName": "류성신",
    "schedules": [
      {
        "days": [
          "TUE",
          "THU"
        ],
        "startTime": "13:30",
        "endTime": "15:20",
        "label": null
      }
    ],
    "room": "문화교실1번",
    "fee": 0,
    "capacity": 20
  },
  {
    "id": "6",
    "name": "요가A(중급)",
    "categoryId": "3",
    "instructorName": "한은경",
    "schedules": [
      {
        "days": [
          "TUE",
          "THU"
        ],
        "startTime": "09:50",
        "endTime": "10:50",
        "label": null
      }
    ],
    "room": "문화교실3번",
    "fee": 60000,
    "capacity": 20
  },
  {
    "id": "7",
    "name": "라인댄스 B",
    "categoryId": "3",
    "instructorName": "정은경",
    "schedules": [
      {
        "days": [
          "TUE",
          "THU"
        ],
        "startTime": "19:00",
        "endTime": "20:30",
        "label": null
      }
    ],
    "room": "문화교실3번",
    "fee": 60000,
    "capacity": 25
  },
  {
    "id": "8",
    "name": "라인댄스 기초",
    "categoryId": "3",
    "instructorName": "정은경",
    "schedules": [
      {
        "days": [
          "MON",
          "WED"
        ],
        "startTime": "10:00",
        "endTime": "11:30",
        "label": null
      }
    ],
    "room": "문화교실3번",
    "fee": 60000,
    "capacity": 25
  },
  {
    "id": "9",
    "name": "방송댄스",
    "categoryId": "3",
    "instructorName": "윤선희",
    "schedules": [
      {
        "days": [
          "MON",
          "WED"
        ],
        "startTime": "19:00",
        "endTime": "20:30",
        "label": null
      }
    ],
    "room": "문화교실3번",
    "fee": 60000,
    "capacity": 25
  },
  {
    "id": "10",
    "name": "싱글댄스(웰빙.라틴)",
    "categoryId": "3",
    "instructorName": "원명호",
    "schedules": [
      {
        "days": [
          "MON",
          "THU"
        ],
        "startTime": "16:00",
        "endTime": "17:30",
        "label": null
      }
    ],
    "room": "문화교실3번",
    "fee": 60000,
    "capacity": 25
  },
  {
    "id": "11",
    "name": "요가B(초급)",
    "categoryId": "3",
    "instructorName": "한은경",
    "schedules": [
      {
        "days": [
          "TUE",
          "THU"
        ],
        "startTime": "11:00",
        "endTime": "12:00",
        "label": null
      }
    ],
    "room": "문화교실3번",
    "fee": 60000,
    "capacity": 20
  },
  {
    "id": "12",
    "name": "한국무용",
    "categoryId": "4",
    "instructorName": "김정희",
    "schedules": [
      {
        "days": [
          "WED"
        ],
        "startTime": "12:00",
        "endTime": "13:30",
        "label": null
      },
      {
        "days": [
          "FRI"
        ],
        "startTime": "10:00",
        "endTime": "11:30",
        "label": null
      }
    ],
    "room": "문화교실3번",
    "fee": 60000,
    "capacity": 25
  },
  {
    "id": "13",
    "name": "시니어모델워킹",
    "categoryId": "4",
    "instructorName": "이제이",
    "schedules": [
      {
        "days": [
          "TUE"
        ],
        "startTime": "14:00",
        "endTime": "16:30",
        "label": null
      }
    ],
    "room": "문화교실3번",
    "fee": 60000,
    "capacity": 25
  },
  {
    "id": "14",
    "name": "장 구 반",
    "categoryId": "4",
    "instructorName": "김정희",
    "schedules": [
      {
        "days": [
          "MON",
          "FRI"
        ],
        "startTime": "12:00",
        "endTime": "13:00",
        "label": null
      }
    ],
    "room": "문화교실3번",
    "fee": 60000,
    "capacity": 20
  },
  {
    "id": "15",
    "name": "기공체조반",
    "categoryId": "3",
    "instructorName": "장세환",
    "schedules": [
      {
        "days": [
          "WED",
          "FRI"
        ],
        "startTime": "16:00",
        "endTime": "17:30",
        "label": null
      }
    ],
    "room": "시간표 미기재",
    "fee": 60000,
    "capacity": 25
  },
  {
    "id": "16",
    "name": "신바람 노래교실A",
    "categoryId": "4",
    "instructorName": "곽인숙",
    "schedules": [
      {
        "days": [
          "TUE"
        ],
        "startTime": "10:00",
        "endTime": "11:30",
        "label": null
      }
    ],
    "room": "문화교실2번",
    "fee": 45000,
    "capacity": 30
  },
  {
    "id": "17",
    "name": "신바람 노래교실B",
    "categoryId": "4",
    "instructorName": "곽인숙",
    "schedules": [
      {
        "days": [
          "THU"
        ],
        "startTime": "10:00",
        "endTime": "11:30",
        "label": null
      }
    ],
    "room": "문화교실2번",
    "fee": 45000,
    "capacity": 30
  },
  {
    "id": "18",
    "name": "모듬북난타",
    "categoryId": "4",
    "instructorName": "오경혜",
    "schedules": [
      {
        "days": [
          "WED",
          "FRI"
        ],
        "startTime": "19:00",
        "endTime": "20:30",
        "label": null
      }
    ],
    "room": "문화교실2번",
    "fee": 60000,
    "capacity": 25
  },
  {
    "id": "19",
    "name": "오카리나",
    "categoryId": "4",
    "instructorName": "도현희",
    "schedules": [
      {
        "days": [
          "WED"
        ],
        "startTime": "10:00",
        "endTime": "11:30",
        "label": "중급"
      },
      {
        "days": [
          "WED"
        ],
        "startTime": "11:30",
        "endTime": "13:00",
        "label": "초급"
      }
    ],
    "room": "문화교실2번",
    "fee": 45000,
    "capacity": 25
  },
  {
    "id": "20",
    "name": "합 창 반",
    "categoryId": "4",
    "instructorName": "안정선",
    "schedules": [
      {
        "days": [
          "THU"
        ],
        "startTime": "13:00",
        "endTime": "14:30",
        "label": null
      }
    ],
    "room": "문화교실2번",
    "fee": 60000,
    "capacity": 30
  },
  {
    "id": "21",
    "name": "캘리그라피",
    "categoryId": "4",
    "instructorName": "김수경",
    "schedules": [
      {
        "days": [
          "WED"
        ],
        "startTime": "14:00",
        "endTime": "15:30",
        "label": "초급"
      },
      {
        "days": [
          "WED"
        ],
        "startTime": "15:30",
        "endTime": "17:00",
        "label": "중급"
      }
    ],
    "room": "문화교실2번",
    "fee": 45000,
    "capacity": 25
  },
  {
    "id": "22",
    "name": "파워디렉터(영상편집)",
    "categoryId": "1",
    "instructorName": "추순자",
    "schedules": [
      {
        "days": [
          "WED",
          "FRI"
        ],
        "startTime": "14:00",
        "endTime": "15:30",
        "label": null
      }
    ],
    "room": "문화교실4번",
    "fee": 60000,
    "capacity": 12
  },
  {
    "id": "23",
    "name": "서양화(수채화)",
    "categoryId": "4",
    "instructorName": "위성웅",
    "schedules": [
      {
        "days": [
          "MON"
        ],
        "startTime": "10:00",
        "endTime": "13:00",
        "label": null
      }
    ],
    "room": "문화교실1번",
    "fee": 60000,
    "capacity": 25
  },
  {
    "id": "24",
    "name": "민 화 반",
    "categoryId": "4",
    "instructorName": "박영선",
    "schedules": [
      {
        "days": [
          "FRI"
        ],
        "startTime": "13:30",
        "endTime": "16:30",
        "label": null
      }
    ],
    "room": "문화교실1번",
    "fee": 60000,
    "capacity": 25
  },
  {
    "id": "25",
    "name": "헬스",
    "categoryId": "3",
    "instructorName": null,
    "schedules": [
      {
        "days": [
          "MON",
          "TUE",
          "WED",
          "THU",
          "FRI"
        ],
        "startTime": "10:00",
        "endTime": "21:00",
        "label": null
      }
    ],
    "room": "체력단련장",
    "fee": 60000,
    "capacity": 180
  }
];
