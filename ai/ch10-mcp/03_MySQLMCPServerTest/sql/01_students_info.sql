-- 学生信息表（容器首次启动时由 /docker-entrypoint-initdb.d 自动导入）
SET NAMES utf8mb4;

DROP TABLE IF EXISTS `students_info`;
CREATE TABLE `students_info` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `StuNum` varchar(255) DEFAULT NULL,
  `StuName` varchar(255) DEFAULT NULL,
  `StuAge` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO `students_info` (`id`, `StuNum`, `StuName`, `StuAge`) VALUES
  (1, '2022001', '张三', '14'),
  (2, '2022002', '李四', '13'),
  (3, '2022003', '王五', '12');
