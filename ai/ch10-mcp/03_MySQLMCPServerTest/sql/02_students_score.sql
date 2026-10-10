-- 学生成绩表
SET NAMES utf8mb4;

DROP TABLE IF EXISTS `students_score`;
CREATE TABLE `students_score` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `StuNum` varchar(255) DEFAULT NULL,
  `score` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO `students_score` (`id`, `StuNum`, `score`) VALUES
  (1, '2022001', '89.3'),
  (2, '2022002', '99.4'),
  (3, '2022003', '39.3');
